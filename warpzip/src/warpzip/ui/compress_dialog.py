"""'Add to archive' dialog."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from ..core.compress import INCOMPRESSIBLE, CompressOptions
from ..core.formats import FORMATS
from ..core.fsutil import human_size
from ..core.security import unique_path
from ..settings import Settings
from . import icons
from .dialogs import message
from .i18n import tr
from .widgets import PasswordEdit, StrengthBar, strength

FORMAT_ORDER = ["zip", "7z", "tar.gz", "tar.xz", "tar.zst", "tar.bz2", "tar"]


def format_hints() -> dict:
    return {
        "zip": tr("어디서나 열려요 (윈도우·맥·폰). 암호는 AES-256으로 안전하게 보호해요.",
                  "Opens everywhere. Passwords use strong AES-256."),
        "7z": tr("가장 작게 압축돼요(느림). 파일 이름까지 암호로 숨길 수 있어요.",
                 "Smallest files (slower). Can even hide file names behind a password."),
        "tar.gz": tr("리눅스/개발자용 표준. 빠르고 가벼워요.", "Developer standard. Fast and light."),
        "tar.xz": tr("리눅스용. 작게 압축되지만 느려요.", "Small output, slower to create."),
        "tar.zst": tr("매우 빠르고 효율적인 최신 형식이에요.", "Very fast, modern and efficient."),
        "tar.bz2": tr("예전 리눅스 형식이에요.", "Classic Linux format."),
        "tar": tr("압축 없이 하나로 묶기만 해요.", "Bundles files without compression."),
    }


def level_presets() -> list:
    return [
        (tr("🚀 워프", "🚀 Warp"), 1, tr("가장 빨라요 · 파일은 조금 커요", "Fastest · slightly bigger files")),
        (tr("표준", "Normal"), 5, tr("속도와 크기의 균형", "Balanced speed and size")),
        (tr("최대", "Maximum"), 7, tr("더 작게 · 조금 느려요", "Smaller · a bit slower")),
        (tr("울트라", "Ultra"), 9, tr("가장 작게 · 오래 걸려요", "Smallest · takes longest")),
        (tr("저장만", "Store"), 0, tr("압축 없이 묶기만 · 즉시 완료", "No compression · instant")),
    ]


SPLIT_SIZES = [
    (tr("나누지 않음", "Don't split"), 0),
    ("100 MB", 100 * 1024 ** 2),
    ("650 MB (CD)", 650 * 1024 ** 2),
    ("700 MB (CD)", 700 * 1024 ** 2),
    (tr("1 GB", "1 GB"), 1024 ** 3),
    (tr("4 GB (FAT32)", "4 GB (FAT32)"), 4 * 1024 ** 3 - 65536),
    ("4.7 GB (DVD)", int(4.7 * 1000 ** 3)),
]


class ScanThread(QThread):
    done = Signal(int, int, int)

    def __init__(self, paths: List[Path]) -> None:
        super().__init__()
        self.paths = paths
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        files = size = incomp = 0
        stack = list(self.paths)
        while stack and not self._stop:
            p = stack.pop()
            try:
                if p.is_dir() and not p.is_symlink():
                    stack.extend(p.iterdir())
                elif p.is_file():
                    files += 1
                    n = p.stat().st_size
                    size += n
                    if p.suffix.lower() in INCOMPRESSIBLE:
                        incomp += n
            except OSError:
                pass
        self.done.emit(files, size, incomp)


class CompressDialog(QDialog):
    def __init__(self, parent, sources: List[Path], settings: Settings,
                 default_dir: Optional[Path] = None, default_name: str = "") -> None:
        super().__init__(parent)
        self.s = settings
        self.sources = [Path(p) for p in sources]
        self.setWindowTitle(tr("압축하기", "Create archive"))
        self.setMinimumWidth(660)
        self._incomp = self._bytes = 0
        self._fmt = settings.get("compress/format")
        if self._fmt not in FORMAT_ORDER:
            self._fmt = "zip"
        self._level = settings.get("compress/level")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(22, 18, 22, 8)
        root.setSpacing(10)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.mascot("happy", 64))
        head.addWidget(pic)
        t = QLabel(tr("어떻게 압축할까요?", "How shall we pack it?"))
        t.setProperty("role", "title")
        head.addWidget(t, 1)
        root.addLayout(head)

        # --- destination ----------------------------------------------------
        g = QGroupBox(tr("저장 위치", "Save to"))
        f = QFormLayout(g)
        f.setHorizontalSpacing(12)
        name = default_name or self._default_name()
        self.name = QLineEdit(name)
        self.ext_lbl = QLabel()
        self.ext_lbl.setProperty("role", "h2")
        nl = QHBoxLayout()
        nl.addWidget(self.name, 1)
        nl.addWidget(self.ext_lbl)
        f.addRow(tr("이름", "Name"), nl)
        self.folder = QLineEdit(str(default_dir or self._default_dir()))
        br = QPushButton(tr("찾아보기", "Browse"))
        br.clicked.connect(self._browse)
        fl = QHBoxLayout()
        fl.addWidget(self.folder, 1)
        fl.addWidget(br)
        f.addRow(tr("폴더", "Folder"), fl)
        root.addWidget(g)

        # --- format chips -----------------------------------------------------
        fr = QHBoxLayout()
        fr.setSpacing(6)
        self.fgroup = QButtonGroup(self)
        self.fbtn = {}
        for key in FORMAT_ORDER:
            b = QToolButton()
            b.setText(FORMATS[key].label)
            b.setCheckable(True)
            b.setProperty("class", "chip")
            b.setCursor(Qt.PointingHandCursor)
            self.fgroup.addButton(b)
            self.fbtn[key] = b
            b.clicked.connect(lambda _=False, k=key: self._set_format(k))
            fr.addWidget(b)
        fr.addStretch(1)
        root.addLayout(fr)
        self.fhint = QLabel()
        self.fhint.setProperty("role", "hint")
        self.fhint.setWordWrap(True)
        root.addWidget(self.fhint)

        # --- level chips ------------------------------------------------------------
        lr = QHBoxLayout()
        lr.setSpacing(6)
        self.lgroup = QButtonGroup(self)
        self.lbtn = {}
        for label, lvl, _hint in level_presets():
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setProperty("class", "chip")
            b.setCursor(Qt.PointingHandCursor)
            self.lgroup.addButton(b)
            self.lbtn[lvl] = b
            b.clicked.connect(lambda _=False, v=lvl: self._set_level(v))
            lr.addWidget(b)
        lr.addStretch(1)
        root.addLayout(lr)
        self.lhint = QLabel()
        self.lhint.setProperty("role", "hint")
        root.addWidget(self.lhint)

        # --- security -------------------------------------------------------------------
        self.sec = QGroupBox(tr("암호 걸기 (선택)", "Password (optional)"))
        sf = QFormLayout(self.sec)
        self.pw = PasswordEdit(tr("비워 두면 암호 없이 압축해요", "Leave empty for no password"))
        self.pw2 = PasswordEdit(tr("비밀번호 확인", "Repeat password"))
        sf.addRow(tr("비밀번호", "Password"), self.pw)
        sf.addRow(tr("확인", "Confirm"), self.pw2)
        self.bar = StrengthBar()
        self.bar_lbl = QLabel("")
        self.bar_lbl.setProperty("role", "hint")
        br2 = QHBoxLayout()
        br2.addWidget(self.bar, 1)
        br2.addWidget(self.bar_lbl)
        sf.addRow("", br2)
        self.enc_names = QCheckBox(tr("파일 이름도 숨기기 (7Z)", "Also hide file names (7Z)"))
        self.enc_names.setChecked(settings.get("compress/encrypt_names"))
        sf.addRow("", self.enc_names)
        self.sec_note = QLabel()
        self.sec_note.setProperty("role", "hint")
        self.sec_note.setWordWrap(True)
        sf.addRow("", self.sec_note)
        self.pw.textChanged.connect(self._pw_changed)
        root.addWidget(self.sec)

        # --- advanced --------------------------------------------------------------------
        self.adv_btn = QToolButton()
        self.adv_btn.setText(tr("고급 옵션", "Advanced options"))
        self.adv_btn.setCheckable(True)
        self.adv_btn.setArrowType(Qt.RightArrow)
        self.adv_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.adv_btn.setAutoRaise(True)
        self.adv_btn.toggled.connect(self._toggle_adv)
        root.addWidget(self.adv_btn, 0, Qt.AlignLeft)
        self.adv = QFrame()
        self.adv.setProperty("role", "card")
        af = QFormLayout(self.adv)
        self.method = QComboBox()
        for lab, key in (("Deflate", "deflate"), ("BZip2", "bzip2"), ("LZMA", "lzma")):
            self.method.addItem(lab, key)
        self.method.setCurrentIndex(max(0, self.method.findData(settings.get("compress/zip_method"))))
        af.addRow(tr("ZIP 방식", "ZIP method"), self.method)
        self.smart = QCheckBox(tr("이미 압축된 파일(JPG·MP4·ZIP…)은 그대로 담기 — 훨씬 빨라져요",
                                  "Store already-compressed files (JPG, MP4, ZIP…) as-is — much faster"))
        self.smart.setChecked(settings.get("compress/smart_store"))
        af.addRow("", self.smart)
        self.split = QComboBox()
        for lab, v in SPLIT_SIZES:
            self.split.addItem(lab, v)
        self.split_custom = QLineEdit()
        self.split_custom.setPlaceholderText(tr("직접 입력 (MB)", "Custom (MB)"))
        self.split_custom.setMaximumWidth(140)
        sl = QHBoxLayout()
        sl.addWidget(self.split)
        sl.addWidget(self.split_custom)
        sl.addStretch(1)
        af.addRow(tr("나누어 압축", "Split volumes"), sl)
        self.exclude = QLineEdit(settings.get("compress/exclude"))
        self.exclude.setToolTip(tr("세미콜론(;)으로 구분, * ? 사용 가능", "Separate with ';', wildcards * ? allowed"))
        af.addRow(tr("제외할 파일", "Exclude"), self.exclude)
        self.comment = QLineEdit()
        af.addRow(tr("설명(ZIP)", "Comment (ZIP)"), self.comment)
        self.del_src = QCheckBox(tr("압축 후 원본을 휴지통으로 보내기", "Move originals to Recycle Bin when done"))
        self.del_src.setChecked(settings.get("compress/delete_sources"))
        af.addRow("", self.del_src)
        self.adv.setVisible(False)
        root.addWidget(self.adv)

        # --- sources ------------------------------------------------------------------------
        sh = QHBoxLayout()
        sh.addWidget(self._h2(tr("압축할 항목", "Items")))
        sh.addStretch(1)
        for text, fn in ((tr("파일 추가", "Add files"), self._add_files), (tr("폴더 추가", "Add folder"), self._add_folder),
                         (tr("제거", "Remove"), self._remove)):
            b = QPushButton(text)
            b.setProperty("class", "flat")
            b.clicked.connect(fn)
            sh.addWidget(b)
        root.addLayout(sh)
        self.list = QListWidget()
        self.list.setMaximumHeight(96)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        root.addWidget(self.list)
        self.total = QLabel("")
        self.total.setProperty("role", "hint")
        root.addWidget(self.total)

        bl = QHBoxLayout()
        bl.setContentsMargins(22, 6, 22, 16)
        bl.addStretch(1)
        c = QPushButton(tr("취소", "Cancel"))
        c.clicked.connect(self.reject)
        self.ok = QPushButton(tr("압축하기", "Compress"))
        self.ok.setProperty("class", "primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._accept)
        bl.addWidget(c)
        bl.addWidget(self.ok)
        outer.addLayout(bl)

        self._scan: Optional[ScanThread] = None
        self._fill_list()
        self._set_format(self._fmt)
        self._set_level(self._level if self._level in self.lbtn else 5)
        self._pw_changed()
        screen = self.screen().availableGeometry() if self.screen() else None
        self.resize(700, min(820, int(screen.height() * 0.9)) if screen else 820)

    # ---- helpers ------------------------------------------------------------------
    @staticmethod
    def _h2(t: str) -> QLabel:
        l = QLabel(t)
        l.setProperty("role", "h2")
        return l

    def _default_name(self) -> str:
        if len(self.sources) == 1:
            return self.sources[0].stem if self.sources[0].is_file() else self.sources[0].name
        return self.sources[0].parent.name or "archive"

    def _default_dir(self) -> Path:
        return self.sources[0].parent if self.sources else Path.home()

    def _toggle_adv(self, on: bool) -> None:
        self.adv.setVisible(on)
        self.adv_btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.adjustSize()

    def _fill_list(self) -> None:
        self.list.clear()
        for p in self.sources:
            it = QListWidgetItem(icons.file_icon(p.name, p.is_dir()), str(p))
            self.list.addItem(it)
        self._rescan()

    def _rescan(self) -> None:
        if self._scan:
            self._scan.stop()
        self.total.setText(tr("크기 계산 중…", "Measuring…"))
        self._scan = ScanThread(list(self.sources))
        self._scan.done.connect(self._scanned)
        self._scan.start()

    def _scanned(self, n: int, b: int, incomp: int) -> None:
        self.total.setText(tr(f"총 {n:,}개 파일 · {human_size(b)}", f"{n:,} files · {human_size(b)}"))
        self._incomp, self._bytes = incomp, b
        self._update_warn()

    def _update_warn(self) -> None:
        slow = self._fmt in ("7z", "tar.xz", "tar.bz2") and self._incomp > 50 * 1024 ** 2 and self._incomp > 0.3 * max(1, self._bytes)
        self.fhint.setText(format_hints()[self._fmt] + (
            tr("\n⚠ 이미 압축된 파일(사진·영상 등)이 많아서 오래 걸릴 수 있어요. ZIP이나 TAR.ZST를 추천해요.",
               "\n⚠ Many already-compressed files (photos, videos): this can be slow. ZIP or TAR.ZST is a better fit.") if slow else ""))

    def _add_files(self) -> None:
        fs, _ = QFileDialog.getOpenFileNames(self, tr("파일 추가", "Add files"))
        self._extend(fs)

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("폴더 추가", "Add folder"))
        self._extend([d] if d else [])

    def _extend(self, paths) -> None:
        for p in paths:
            pp = Path(p)
            if pp not in self.sources:
                self.sources.append(pp)
        self._fill_list()

    def _remove(self) -> None:
        for it in self.list.selectedItems():
            p = Path(it.text())
            if p in self.sources and len(self.sources) > 1:
                self.sources.remove(p)
        self._fill_list()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("저장할 폴더", "Destination folder"), self.folder.text())
        if d:
            self.folder.setText(d)

    # ---- state ----------------------------------------------------------------------------
    def _set_format(self, key: str) -> None:
        self._fmt = key
        info = FORMATS[key]
        self.fbtn[key].setChecked(True)
        self.ext_lbl.setText(info.ext)
        self._update_warn()
        is_tar = key.startswith("tar")
        self.sec.setEnabled(not is_tar)
        self.enc_names.setEnabled(key == "7z")
        self.method.setEnabled(key == "zip")
        self.smart.setEnabled(key == "zip")
        for b in self.lbtn.values():
            b.setEnabled(key != "tar")
        if is_tar:
            self.sec_note.setText(tr("TAR 형식은 암호를 지원하지 않아요. ZIP 또는 7Z를 선택하세요.",
                                     "TAR formats can't be encrypted. Choose ZIP or 7Z."))
        else:
            self.sec_note.setText("AES-256")
        if key == "tar":
            self.lhint.setText(tr("압축 없음", "No compression"))
        else:
            self._set_level(self._level if self._level in self.lbtn else 5)

    def _set_level(self, lvl: int) -> None:
        self._level = lvl
        self.lbtn[lvl].setChecked(True)
        for _l, v, h in level_presets():
            if v == lvl and self._fmt != "tar":
                self.lhint.setText(h)

    def _pw_changed(self) -> None:
        sc, label = strength(self.pw.text())
        self.bar.set_score(sc)
        self.bar_lbl.setText(label)

    # ---- result --------------------------------------------------------------------------------
    def _split_bytes(self) -> int:
        txt = self.split_custom.text().strip()
        if txt:
            try:
                return max(1, int(float(txt) * 1024 * 1024))
            except ValueError:
                return 0
        return int(self.split.currentData() or 0)

    def destination(self) -> Path:
        name = self.name.text().strip() or "archive"
        return Path(self.folder.text().strip()) / (name + FORMATS[self._fmt].ext)

    def options(self) -> CompressOptions:
        pw = self.pw.text() if not self._fmt.startswith("tar") else ""
        return CompressOptions(
            fmt=self._fmt, level=self._level,
            zip_method=self.method.currentData(), password=pw or None,
            encrypt_names=self.enc_names.isChecked() and self._fmt == "7z",
            split_size=self._split_bytes(),
            exclude=[x.strip() for x in self.exclude.text().split(";") if x.strip()],
            smart_store=self.smart.isChecked(), delete_sources=self.del_src.isChecked(),
            comment=self.comment.text(),
        )

    def _accept(self) -> None:
        if self.pw.text() != self.pw2.text() and not self._fmt.startswith("tar"):
            message(self, "warning", tr("비밀번호 확인", "Password check"),
                    tr("비밀번호 두 칸이 서로 달라요. 다시 확인해 주세요.", "The two passwords don't match."))
            return
        dest = self.destination()
        if not dest.parent.exists():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
            except OSError as ex:
                message(self, "error", tr("폴더를 만들 수 없어요", "Can't create folder"), str(ex))
                return
        if any(dest == s or s in dest.parents and s.is_file() for s in self.sources):
            message(self, "warning", tr("저장 위치 확인", "Check destination"),
                    tr("압축 파일이 압축 대상 안에 있어요. 다른 위치를 선택하세요.", "Destination is inside the items."))
            return
        if dest.exists():
            i = message(self, "ask", tr("같은 이름의 파일이 있어요", "File already exists"),
                        tr(f"'{dest.name}' 파일이 이미 있어요.\n어떻게 할까요?", f"'{dest.name}' already exists.\nWhat now?"),
                        buttons=[(tr("취소", "Cancel"), "normal"), (tr("이름 바꿔 저장", "Keep both"), "normal"),
                                 (tr("덮어쓰기", "Overwrite"), "danger")])
            if i == 1:
                self._rename_to = unique_path(dest)
                self.name.setText(self._rename_to.name[: -len(FORMATS[self._fmt].ext)])
            elif i != 2:
                return
        self.s.set("compress/format", self._fmt)
        self.s.set("compress/level", self._level)
        self.s.set("compress/zip_method", self.method.currentData())
        self.s.set("compress/smart_store", self.smart.isChecked())
        self.s.set("compress/exclude", self.exclude.text())
        self.s.set("compress/delete_sources", self.del_src.isChecked())
        self.s.set("compress/encrypt_names", self.enc_names.isChecked())
        if self._scan:
            self._scan.stop()
        self.accept()

    def reject(self) -> None:
        if self._scan:
            self._scan.stop()
            self._scan.wait(500)
        super().reject()

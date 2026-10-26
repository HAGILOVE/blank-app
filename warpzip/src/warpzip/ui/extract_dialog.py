"""'Extract to…' dialog."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QToolButton, QVBoxLayout,
)

from ..core import encoding as enc
from ..core.fsutil import human_size
from ..core.sink import ExtractOptions
from ..settings import Settings
from . import icons
from .i18n import tr
from .widgets import ElidedLabel

EXEC_EXT = {"exe", "msi", "bat", "cmd", "ps1", "vbs", "js", "jar", "scr", "com", "lnk", "reg", "hta", "wsf"}


class ExtractDialog(QDialog):
    def __init__(self, parent, archive: Path, settings: Settings, files: int, size: int,
                 encrypted: bool, selected: int = 0, has_exec: bool = False,
                 detected_encoding: Optional[str] = None, is_zip: bool = False) -> None:
        super().__init__(parent)
        self.s = settings
        self.archive = archive
        self.setWindowTitle(tr("압축 풀기", "Extract"))
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.mascot("idle", 64))
        head.addWidget(pic)
        col = QVBoxLayout()
        t = QLabel(tr("어디에 풀까요?", "Where to unpack?"))
        t.setProperty("role", "title")
        col.addWidget(t)
        info = tr(f"{archive.name} · {files:,}개 파일 · {human_size(size)}",
                  f"{archive.name} · {files:,} files · {human_size(size)}")
        if selected:
            info += tr(f"  (선택한 {selected:,}개만 풀어요)", f"  (only {selected:,} selected)")
        il = ElidedLabel(info)
        il.setProperty("role", "sub")
        col.addWidget(il)
        head.addLayout(col, 1)
        root.addLayout(head)

        g = QGroupBox(tr("풀 위치", "Destination"))
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        self.dest = QComboBox()
        self.dest.setEditable(True)
        self.dest.setInsertPolicy(QComboBox.NoInsert)
        same = str(archive.parent)
        recents = [same] + [d for d in settings.get_list("extract/recent_dests") if d != same]
        self.dest.addItems(recents)
        if settings.get("extract/dest_mode") == "last" and settings.get("extract/last_dest"):
            self.dest.setCurrentText(settings.get("extract/last_dest"))
        br = QPushButton(tr("찾아보기", "Browse"))
        br.clicked.connect(self._browse)
        row.addWidget(self.dest, 1)
        row.addWidget(br)
        gl.addLayout(row)
        quick = QHBoxLayout()
        for label, sp in ((tr("압축 파일 옆", "Next to archive"), None),
                          (tr("바탕화면", "Desktop"), QStandardPaths.DesktopLocation),
                          (tr("문서", "Documents"), QStandardPaths.DocumentsLocation),
                          (tr("다운로드", "Downloads"), QStandardPaths.DownloadLocation)):
            b = QPushButton(label)
            b.setProperty("class", "flat")
            path = same if sp is None else QStandardPaths.writableLocation(sp)
            b.clicked.connect(lambda _=False, p=path: self.dest.setCurrentText(p))
            quick.addWidget(b)
        quick.addStretch(1)
        gl.addLayout(quick)
        root.addWidget(g)

        # folder mode
        self.fgroup = QButtonGroup(self)
        fm = QHBoxLayout()
        fm.setSpacing(6)
        self.fbtn = {}
        for key, label in (("smart", tr("✨ 스마트", "✨ Smart")), ("always", tr("📁 새 폴더에 풀기", "📁 Into new folder")),
                           ("never", tr("바로 풀기", "Directly"))):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setProperty("class", "chip")
            self.fgroup.addButton(b)
            self.fbtn[key] = b
            b.clicked.connect(lambda _=False, k=key: self._set_mode(k))
            fm.addWidget(b)
        fm.addStretch(1)
        root.addLayout(fm)
        self.mode_hint = QLabel()
        self.mode_hint.setProperty("role", "hint")
        root.addWidget(self.mode_hint)
        self._mode = settings.get("extract/folder_mode")
        if self._mode not in self.fbtn:
            self._mode = "smart"
        self._set_mode(self._mode)

        form = QFormLayout()
        self.over = QComboBox()
        for label, key in ((tr("이름을 바꿔서 둘 다 보관 (추천)", "Keep both (rename)"), "rename"),
                           (tr("덮어쓰기", "Overwrite"), "overwrite"), (tr("건너뛰기", "Skip"), "skip"),
                           (tr("더 최신 파일만 덮어쓰기", "Overwrite if newer"), "newer")):
            self.over.addItem(label, key)
        self.over.setCurrentIndex(max(0, self.over.findData(settings.get("extract/overwrite"))))
        form.addRow(tr("같은 이름이 있을 때", "If file exists"), self.over)
        self.enc = QComboBox()
        for label, codec in enc.CHOICES:
            self.enc.addItem(label if codec != "auto" else tr("자동 감지", "Auto-detect"), codec)
        self.enc.setEnabled(is_zip)
        if is_zip and detected_encoding and detected_encoding != "utf-8":
            self.enc.setToolTip(tr(f"자동 감지: {detected_encoding}", f"Detected: {detected_encoding}"))
        form.addRow(tr("파일 이름 인코딩", "File name encoding"), self.enc)
        root.addLayout(form)

        self.open_after = QCheckBox(tr("완료 후 폴더 열기", "Open folder when done"))
        self.open_after.setChecked(settings.get("extract/open_folder"))
        self.del_after = QCheckBox(tr("완료 후 압축 파일을 휴지통으로 보내기", "Move archive to Recycle Bin when done"))
        self.del_after.setChecked(settings.get("extract/delete_archive"))
        self.motw = QCheckBox(tr("다운로드 표시(보안 경고) 유지하기 — 안전을 위해 권장", "Keep 'downloaded from internet' mark (recommended)"))
        self.motw.setChecked(settings.get("extract/motw"))
        for w in (self.open_after, self.del_after, self.motw):
            root.addWidget(w)
        if has_exec:
            warn = QLabel(tr("⚠ 실행 파일(.exe 등)이 들어 있어요. 믿을 수 있는 압축 파일인지 확인하세요.",
                             "⚠ Contains executable files. Make sure you trust this archive."))
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#E08A00;font-weight:700")
            root.addWidget(warn)

        bl = QHBoxLayout()
        bl.addStretch(1)
        c = QPushButton(tr("취소", "Cancel"))
        c.clicked.connect(self.reject)
        ok = QPushButton(tr("풀기", "Extract"))
        ok.setProperty("class", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        bl.addWidget(c)
        bl.addWidget(ok)
        root.addLayout(bl)

    def _set_mode(self, key: str) -> None:
        self._mode = key
        self.fbtn[key].setChecked(True)
        self.mode_hint.setText({
            "smart": tr("파일이 여러 개면 압축 파일 이름의 폴더를 만들어 풀어요. 폴더 하나만 있으면 그대로 풀어요.",
                        "Makes a folder only when the archive has several top-level items."),
            "always": tr("항상 압축 파일 이름의 새 폴더 안에 풀어요.", "Always unpack into a folder named after the archive."),
            "never": tr("선택한 위치에 바로 풀어요.", "Unpack straight into the chosen folder."),
        }[key])

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("풀 폴더 선택", "Choose folder"), self.dest.currentText())
        if d:
            self.dest.setCurrentText(d)

    def _accept(self) -> None:
        d = self.dest.currentText().strip().strip('"')
        if not d:
            return
        self.s.push_recent("extract/recent_dests", d)
        self.s.set("extract/last_dest", d)
        self.s.set("extract/folder_mode", self._mode)
        self.s.set("extract/overwrite", self.over.currentData())
        self.s.set("extract/open_folder", self.open_after.isChecked())
        self.s.set("extract/delete_archive", self.del_after.isChecked())
        self.s.set("extract/motw", self.motw.isChecked())
        self.accept()

    def destination(self) -> Path:
        return Path(self.dest.currentText().strip().strip('"'))

    def options(self) -> ExtractOptions:
        codec = self.enc.currentData()
        return ExtractOptions(folder_mode=self._mode, overwrite=self.over.currentData(),
                              encoding=None if codec == "auto" else codec,
                              propagate_motw=self.motw.isChecked())

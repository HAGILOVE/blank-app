"""Small dialogs: mascot message box, password prompt, info, hash, about."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .. import APP_NAME, APP_NAME_KO, __version__
from . import icons
from .i18n import tr
from .widgets import ElidedLabel, PasswordEdit

MOOD_FOR = {"info": "idle", "success": "happy", "warning": "work", "error": "sad", "ask": "idle", "sleep": "sleep"}


class MascotMessage(QDialog):
    """Message box with Warpy. ``buttons`` = [(label, kind)] where kind in primary/danger/normal."""

    def __init__(self, parent, kind: str, title: str, text: str, details: str = "",
                 buttons: Optional[Sequence[tuple]] = None, check: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.result_index = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        row = QHBoxLayout()
        row.setSpacing(18)
        pic = QLabel()
        pic.setPixmap(icons.mascot(MOOD_FOR.get(kind, "idle"), 92))
        pic.setAlignment(Qt.AlignTop)
        row.addWidget(pic)
        col = QVBoxLayout()
        t = QLabel(title)
        t.setProperty("role", "h2")
        col.addWidget(t)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setMinimumWidth(300)
        col.addWidget(body)
        col.addStretch(1)
        row.addLayout(col, 1)
        root.addLayout(row)
        self.details = None
        if details:
            self.details = QPlainTextEdit(details)
            self.details.setReadOnly(True)
            self.details.setMaximumHeight(130)
            root.addWidget(self.details)
        self.checkbox = None
        if check:
            self.checkbox = QCheckBox(check)
            root.addWidget(self.checkbox)
        bl = QHBoxLayout()
        bl.addStretch(1)
        for i, (label, bkind) in enumerate(buttons or [(tr("확인", "OK"), "primary")]):
            b = QPushButton(label)
            if bkind in ("primary", "danger"):
                b.setProperty("class", bkind)
            b.clicked.connect(lambda _=False, i=i: self._pick(i))
            if bkind == "primary":
                b.setDefault(True)
            bl.addWidget(b)
        root.addLayout(bl)

    def _pick(self, i: int) -> None:
        self.result_index = i
        self.accept()

    @property
    def checked(self) -> bool:
        return bool(self.checkbox and self.checkbox.isChecked())


def message(parent, kind: str, title: str, text: str, details: str = "",
            buttons: Optional[Sequence[tuple]] = None, check: str = "") -> int:
    dlg = MascotMessage(parent, kind, title, text, details, buttons, check)
    dlg.exec()
    message.checked = dlg.checked  # type: ignore[attr-defined]
    return dlg.result_index


def confirm(parent, title: str, text: str, yes: str = "", no: str = "", danger: bool = False) -> bool:
    i = message(parent, "ask", title, text, buttons=[(no or tr("취소", "Cancel"), "normal"),
                                                    (yes or tr("확인", "OK"), "danger" if danger else "primary")])
    return i == 1


class PasswordDialog(QDialog):
    def __init__(self, parent, archive_name: str, wrong: bool = False, remember_default: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("비밀번호 입력", "Enter password"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        row = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.pixmap("lock", 64, dpr=2))
        row.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        h = QLabel(tr("암호로 보호된 압축 파일이에요", "This archive is password protected"))
        h.setProperty("role", "h2")
        col.addWidget(h)
        col.addWidget(ElidedLabel(archive_name))
        row.addLayout(col, 1)
        lay.addLayout(row)
        self.pw = PasswordEdit(tr("비밀번호", "Password"))
        lay.addWidget(self.pw)
        self.err = QLabel(tr("비밀번호가 맞지 않아요. 다시 입력해 주세요.", "Wrong password. Please try again."))
        self.err.setStyleSheet("color:#FF6B81;font-weight:600")
        self.err.setVisible(wrong)
        lay.addWidget(self.err)
        self.remember = QCheckBox(tr("이번 실행 동안 기억하기", "Remember for this session"))
        self.remember.setChecked(remember_default)
        lay.addWidget(self.remember)
        bl = QHBoxLayout()
        bl.addStretch(1)
        c = QPushButton(tr("취소", "Cancel"))
        c.clicked.connect(self.reject)
        ok = QPushButton(tr("확인", "OK"))
        ok.setProperty("class", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bl.addWidget(c)
        bl.addWidget(ok)
        lay.addLayout(bl)
        self.pw.setFocus()

    def password(self) -> str:
        return self.pw.text()


def ask_password(parent, archive_name: str, wrong: bool = False) -> Optional[tuple]:
    d = PasswordDialog(parent, archive_name, wrong, remember_default=True)
    if d.exec() == QDialog.Accepted and d.password():
        return d.password(), d.remember.isChecked()
    return None


class InfoDialog(QDialog):
    def __init__(self, parent, rows: Sequence[tuple], title: str, header: str = "", comment: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        top = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.mascot("idle", 72))
        top.addWidget(pic)
        h = QLabel(header)
        h.setProperty("role", "title")
        h.setWordWrap(True)
        top.addWidget(h, 1)
        lay.addLayout(top)
        card = QFrame()
        card.setProperty("role", "card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setVerticalSpacing(8)
        for i, (k, v) in enumerate(rows):
            kl = QLabel(k)
            kl.setProperty("role", "sub")
            vl = QLabel(str(v))
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(kl, i, 0, Qt.AlignTop)
            grid.addWidget(vl, i, 1)
        grid.setColumnStretch(1, 1)
        lay.addWidget(card)
        if comment:
            c = QPlainTextEdit(comment)
            c.setReadOnly(True)
            c.setMaximumHeight(90)
            lay.addWidget(c)
        bl = QHBoxLayout()
        bl.addStretch(1)
        ok = QPushButton(tr("닫기", "Close"))
        ok.setProperty("class", "primary")
        ok.clicked.connect(self.accept)
        bl.addWidget(ok)
        lay.addLayout(bl)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("워프집 정보", "About WARPZIP"))
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        pic = QLabel()
        pic.setPixmap(icons.mascot("happy", 150))
        pic.setAlignment(Qt.AlignCenter)
        lay.addWidget(pic)
        t = QLabel(f"{APP_NAME}  {APP_NAME_KO}")
        t.setProperty("role", "title")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        v = QLabel(tr(f"버전 {__version__}  ·  워프 속도로 압축하고 푸는 귀여운 압축 프로그램",
                      f"Version {__version__}  ·  The cute archive manager at warp speed"))
        v.setProperty("role", "sub")
        v.setAlignment(Qt.AlignCenter)
        v.setWordWrap(True)
        lay.addWidget(v)
        notes = QPlainTextEdit()
        notes.setReadOnly(True)
        notes.setMaximumHeight(150)
        notes.setPlainText(
            "Open-source components\n"
            "  PySide6 / Qt (LGPLv3) · py7zr (LGPLv2.1+) · pyzipper (MIT) · zstandard (BSD)\n"
            "  7-Zip engine for RAR/ISO/CAB… (LGPL + unRAR restriction) — optional\n\n"
            + tr("자세한 라이선스는 설치 폴더의 THIRD_PARTY_NOTICES.md 를 확인하세요.",
                 "See THIRD_PARTY_NOTICES.md in the install folder for full licences."))
        lay.addWidget(notes)
        bl = QHBoxLayout()
        bl.addStretch(1)
        ok = QPushButton(tr("닫기", "Close"))
        ok.setProperty("class", "primary")
        ok.clicked.connect(self.accept)
        bl.addWidget(ok)
        bl.addStretch(1)
        lay.addLayout(bl)


class HashDialog(QDialog):
    """Compute and compare checksums of a file."""

    def __init__(self, parent, path: str = "") -> None:
        super().__init__(parent)
        from ..core.hashing import ALGORITHMS

        self.setWindowTitle(tr("체크섬(해시) 계산", "Checksums"))
        self.setMinimumWidth(640)
        self._algos = ALGORITHMS
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        row = QHBoxLayout()
        self.path = QLineEdit(path)
        self.path.setPlaceholderText(tr("파일 경로", "File path"))
        b = QPushButton(tr("찾아보기", "Browse"))
        b.clicked.connect(self._browse)
        go = QPushButton(tr("계산", "Compute"))
        go.setProperty("class", "primary")
        go.clicked.connect(self._compute)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        row.addWidget(go)
        lay.addLayout(row)
        self.fields = {}
        form = QFormLayout()
        for a in self._algos:
            e = QLineEdit()
            e.setReadOnly(True)
            e.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace;")
            cp = QPushButton(tr("복사", "Copy"))
            cp.setProperty("class", "flat")
            cp.clicked.connect(lambda _=False, e=e: QGuiApplication.clipboard().setText(e.text()))
            hl = QHBoxLayout()
            hl.addWidget(e, 1)
            hl.addWidget(cp)
            form.addRow(a, hl)
            self.fields[a] = e
        lay.addLayout(form)
        self.cmp = QLineEdit()
        self.cmp.setPlaceholderText(tr("비교할 해시값을 붙여넣으세요", "Paste an expected hash to compare"))
        self.cmp.textChanged.connect(self._compare)
        lay.addWidget(self.cmp)
        self.status = QLabel("")
        lay.addWidget(self.status)
        bl = QHBoxLayout()
        bl.addStretch(1)
        ok = QPushButton(tr("닫기", "Close"))
        ok.clicked.connect(self.accept)
        bl.addWidget(ok)
        lay.addLayout(bl)
        if path:
            self._compute()

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, tr("파일 선택", "Select file"))
        if f:
            self.path.setText(f)
            self._compute()

    def _compute(self) -> None:
        from ..core.hashing import hash_file
        from .progress_dialog import run_job

        p = Path(self.path.text().strip().strip('"'))
        if not p.is_file():
            self.status.setText(tr("파일을 찾을 수 없어요.", "File not found."))
            return
        out = run_job(self, tr("해시 계산 중", "Computing checksums"), p.name,
                      lambda cb, cancel: hash_file(p, progress=cb, cancel=cancel), kind="hash")
        if out.ok:
            for a, e in self.fields.items():
                e.setText(out.result.get(a, ""))
            self._compare()

    def _compare(self) -> None:
        want = self.cmp.text().strip().lower().replace(" ", "")
        if not want:
            self.status.setText("")
            return
        hit = next((a for a, e in self.fields.items() if e.text().lower() == want), None)
        if hit:
            self.status.setText(f"✔ {tr('일치해요!', 'Match!')} ({hit})")
            self.status.setStyleSheet("color:#35C98B;font-weight:700")
        else:
            self.status.setText(f"✘ {tr('일치하지 않아요.', 'No match.')}")
            self.status.setStyleSheet("color:#FF6B81;font-weight:700")

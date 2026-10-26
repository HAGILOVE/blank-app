"""Preferences dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.formats import ASSOCIABLE
from ..settings import Settings
from ..shell import windows_integration as wi
from . import icons
from .dialogs import message
from .i18n import language, tr


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: Settings) -> None:
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle(tr("설정", "Settings"))
        self.setMinimumWidth(560)
        self.changed_ui = False
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.pixmap("settings", 44))
        head.addWidget(pic)
        t = QLabel(tr("설정", "Settings"))
        t.setProperty("role", "title")
        head.addWidget(t, 1)
        root.addLayout(head)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # general ---------------------------------------------------------------------------
        gen = QWidget()
        f = QFormLayout(gen)
        f.setContentsMargins(16, 16, 16, 16)
        self.lang = QComboBox()
        for lab, key in ((tr("시스템 설정 따르기", "Follow system"), "auto"), ("한국어", "ko"), ("English", "en")):
            self.lang.addItem(lab, key)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings.get("language"))))
        f.addRow(tr("언어", "Language"), self.lang)
        self.theme = QComboBox()
        for lab, key in ((tr("시스템 설정 따르기", "Follow system"), "auto"), (tr("밝은 테마", "Light"), "light"), (tr("어두운 테마", "Dark"), "dark")):
            self.theme.addItem(lab, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.get("theme"))))
        f.addRow(tr("테마", "Theme"), self.theme)
        self.auto_close = QCheckBox(tr("작업이 끝나면 진행 창을 자동으로 닫기", "Close the progress window automatically"))
        self.auto_close.setChecked(settings.get("ui/auto_close_progress"))
        f.addRow("", self.auto_close)
        self.preview = QCheckBox(tr("미리보기 창 보이기", "Show preview pane"))
        self.preview.setChecked(settings.get("ui/show_preview"))
        f.addRow("", self.preview)
        tabs.addTab(gen, tr("일반", "General"))

        # defaults -------------------------------------------------------------------------------
        dfl = QWidget()
        d = QFormLayout(dfl)
        d.setContentsMargins(16, 16, 16, 16)
        self.fmode = QComboBox()
        for lab, key in ((tr("스마트", "Smart"), "smart"), (tr("항상 새 폴더", "Always new folder"), "always"), (tr("폴더 없이", "No folder"), "never")):
            self.fmode.addItem(lab, key)
        self.fmode.setCurrentIndex(max(0, self.fmode.findData(settings.get("extract/folder_mode"))))
        d.addRow(tr("풀기 기본 방식", "Default extract mode"), self.fmode)
        self.over = QComboBox()
        for lab, key in ((tr("이름 바꿔 보관", "Keep both"), "rename"), (tr("덮어쓰기", "Overwrite"), "overwrite"), (tr("건너뛰기", "Skip"), "skip"), (tr("최신 파일만", "If newer"), "newer")):
            self.over.addItem(lab, key)
        self.over.setCurrentIndex(max(0, self.over.findData(settings.get("extract/overwrite"))))
        d.addRow(tr("같은 이름 처리", "If file exists"), self.over)
        self.motw = QCheckBox(tr("다운로드 표시(Mark-of-the-Web) 유지", "Keep Mark-of-the-Web"))
        self.motw.setChecked(settings.get("extract/motw"))
        d.addRow("", self.motw)
        tabs.addTab(dfl, tr("기본값", "Defaults"))

        # windows --------------------------------------------------------------------------------------
        win = QWidget()
        w = QVBoxLayout(win)
        w.setContentsMargins(16, 16, 16, 16)
        info = QLabel(tr("탐색기 우클릭 메뉴와 파일 연결은 현재 사용자 계정에만 적용돼요 (관리자 권한 불필요).",
                         "Explorer menu entries and file types apply to the current user only (no admin needed)."))
        info.setWordWrap(True)
        info.setProperty("role", "sub")
        w.addWidget(info)
        self.menu_state = QLabel("")
        w.addWidget(self.menu_state)
        row = QHBoxLayout()
        b1 = QPushButton(tr("우클릭 메뉴 추가", "Add context menu"))
        b1.setProperty("class", "primary")
        b1.clicked.connect(self._install_menu)
        b2 = QPushButton(tr("제거", "Remove"))
        b2.clicked.connect(self._remove_menu)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        w.addLayout(row)
        w.addSpacing(10)
        w.addWidget(QLabel(tr("연결할 파일 형식", "File types to associate")))
        self.ext_boxes = []
        grid = QHBoxLayout()
        col1, col2, col3 = QVBoxLayout(), QVBoxLayout(), QVBoxLayout()
        for i, ext in enumerate(ASSOCIABLE):
            cb = QCheckBox(ext)
            cb.setChecked(ext in (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".001"))
            self.ext_boxes.append(cb)
            (col1, col2, col3)[i % 3].addWidget(cb)
        for c in (col1, col2, col3):
            grid.addLayout(c)
        w.addLayout(grid)
        row2 = QHBoxLayout()
        b3 = QPushButton(tr("파일 연결 등록", "Register file types"))
        b3.clicked.connect(self._assoc)
        row2.addWidget(b3)
        row2.addStretch(1)
        w.addLayout(row2)
        hint = QLabel(tr("윈도우는 보안상 기본 앱을 직접 바꾸지 못하게 해요. 등록 후 열리는 '기본 앱' 설정에서 WARPZIP을 선택해 주세요.",
                         "Windows doesn't let apps change defaults themselves. After registering, pick WARPZIP in the Default apps page that opens."))
        hint.setWordWrap(True)
        hint.setProperty("role", "hint")
        w.addWidget(hint)
        w.addStretch(1)
        win.setEnabled(wi.IS_WINDOWS)
        tabs.addTab(win, tr("윈도우 연동", "Windows"))
        self._refresh_menu_state()

        bl = QHBoxLayout()
        bl.addStretch(1)
        c = QPushButton(tr("취소", "Cancel"))
        c.clicked.connect(self.reject)
        ok = QPushButton(tr("저장", "Save"))
        ok.setProperty("class", "primary")
        ok.clicked.connect(self._save)
        bl.addWidget(c)
        bl.addWidget(ok)
        root.addLayout(bl)

    def _refresh_menu_state(self) -> None:
        if not wi.IS_WINDOWS:
            self.menu_state.setText(tr("윈도우에서만 사용할 수 있어요.", "Available on Windows only."))
            return
        on = wi.context_menu_installed()
        self.menu_state.setText(tr("✔ 우클릭 메뉴가 설치되어 있어요", "✔ Context menu installed") if on else tr("우클릭 메뉴가 설치되어 있지 않아요", "Context menu not installed"))

    def _install_menu(self) -> None:
        wi.install_context_menu(language())
        self._refresh_menu_state()
        message(self, "success", tr("완료!", "Done!"), tr("파일/폴더를 우클릭하면 WARPZIP 메뉴가 나와요.\n(윈도우 11은 '더 보기 옵션'에서 볼 수 있어요)", "Right-click a file or folder.\n(On Windows 11 look under 'Show more options')"))

    def _remove_menu(self) -> None:
        wi.uninstall_context_menu()
        self._refresh_menu_state()

    def _assoc(self) -> None:
        exts = [cb.text() for cb in self.ext_boxes if cb.isChecked()]
        wi.register_associations(exts, language())
        wi.open_default_apps_settings()

    def _save(self) -> None:
        old = (self.s.get("language"), self.s.get("theme"), self.s.get("ui/show_preview"))
        self.s.set("language", self.lang.currentData())
        self.s.set("theme", self.theme.currentData())
        self.s.set("ui/auto_close_progress", self.auto_close.isChecked())
        self.s.set("ui/show_preview", self.preview.isChecked())
        self.s.set("extract/folder_mode", self.fmode.currentData())
        self.s.set("extract/overwrite", self.over.currentData())
        self.s.set("extract/motw", self.motw.isChecked())
        self.changed_ui = old != (self.lang.currentData(), self.theme.currentData(), self.preview.isChecked())
        self.accept()

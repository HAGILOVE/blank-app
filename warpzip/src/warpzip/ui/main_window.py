"""The main WARPZIP window: welcome screen + archive browser."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QMimeData, QModelIndex, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDrag, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QTableView, QToolBar, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_NAME_KO
from ..core import archive as ar
from ..core import encoding as enc
from ..core.archive import analyze
from ..core.formats import sniff_path
from ..core.fsutil import human_size
from ..core.readers import ArchiveReader
from ..core.sink import ExtractOptions
from ..settings import Settings
from . import icons
from .actions import Actions
from .archive_model import ArchiveModel, ArchiveProxy, ArchiveTree, Node
from .dialogs import AboutDialog, HashDialog, InfoDialog, confirm, message
from .i18n import tr
from .preview import PreviewPanel
from .progress_dialog import run_job
from .settings_dialog import SettingsDialog
from .widgets import DropZone


class ArchiveTable(QTableView):
    """Table that can drag selected members out to Explorer."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.win = window
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, _actions) -> None:  # noqa: N802
        urls = self.win.stage_selection_for_drag()
        if not urls:
            return
        mime = QMimeData()
        mime.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class MainWindow(QMainWindow):
    settings_changed = Signal()

    def __init__(self, settings: Settings, actions: Actions) -> None:
        super().__init__()
        self.s = settings
        self.actions = actions
        self.reader: Optional[ArchiveReader] = None
        self.tree: Optional[ArchiveTree] = None
        self.history: List[str] = []
        self._drag_dirs: List[Path] = []
        self.setWindowTitle(f"{APP_NAME} {APP_NAME_KO}")
        self.setWindowIcon(icons.app_icon())
        self.setAcceptDrops(True)
        self.resize(1080, 700)
        self.setMinimumSize(760, 520)
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_status()
        self._update_state()
        geo = self.s.get("ui/geometry")
        if geo:
            self.restoreGeometry(geo)

    # ================================================================== construction
    def _act(self, icon: str, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        a = QAction(icons.icon(icon) if icon else QAction().icon(), text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip(tip or text)
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        A = self._act
        self.a_open = A("open", tr("열기", "Open"), self.act_open, "Ctrl+O", tr("압축 파일 열기 (Ctrl+O)", "Open archive (Ctrl+O)"))
        self.a_new = A("add", tr("압축하기", "Compress"), self.act_new, "Ctrl+N", tr("새로 압축하기 (Ctrl+N)", "New archive (Ctrl+N)"))
        self.a_extract = A("extract", tr("풀기", "Extract"), self.act_extract_all, "Ctrl+E", tr("모두 풀기 (Ctrl+E)", "Extract all (Ctrl+E)"))
        self.a_extract_sel = A("extract_here", tr("선택 풀기", "Extract selected"), self.act_extract_selected, "Ctrl+Shift+E")
        self.a_add = A("add_file", tr("파일 추가", "Add files"), self.act_add_files, "Ctrl+Shift+A", tr("압축 파일에 파일 추가 (ZIP)", "Add files to archive (ZIP)"))
        self.a_add_dir = A("add_folder", tr("폴더 추가", "Add folder"), self.act_add_folder)
        self.a_delete = A("delete", tr("삭제", "Delete"), self.act_delete, "Del", tr("압축 파일에서 삭제 (ZIP)", "Delete from archive (ZIP)"))
        self.a_rename = A("rename", tr("이름 바꾸기", "Rename"), self.act_rename, "F2")
        self.a_test = A("test", tr("검사", "Test"), self.act_test, "Ctrl+T", tr("무결성 검사 (Ctrl+T)", "Integrity test (Ctrl+T)"))
        self.a_info = A("info", tr("정보", "Info"), self.act_info, "Ctrl+I")
        self.a_hash = A("hash", tr("체크섬", "Checksums"), self.act_hash)
        self.a_convert = A("convert", tr("형식 변환", "Convert format"), self.act_convert)
        self.a_repair = A("test", tr("손상된 ZIP 복구…", "Repair damaged ZIP…"), self.act_repair)
        self.a_close = A("", tr("압축 파일 닫기", "Close archive"), self.close_archive, "Ctrl+W")
        self.a_settings = A("settings", tr("설정", "Settings"), self.act_settings, "Ctrl+,")
        self.a_about = A("star", tr("워프집 정보", "About WARPZIP"), self.act_about, "F1")
        self.a_exit = A("", tr("끝내기", "Exit"), self.close, "Ctrl+Q")
        self.a_up = A("up", tr("위로", "Up"), self.go_up, "Backspace")
        self.a_back = A("back", tr("뒤로", "Back"), self.go_back, "Alt+Left")
        self.a_search = A("search", tr("검색", "Search"), lambda: self.search.setFocus(), "Ctrl+F")
        self.a_copy_path = A("copy", tr("경로 복사", "Copy path"), self.act_copy_path)
        self.a_open_file = A("open", tr("열기", "Open"), self.act_open_selected, "Return")
        self.a_preview = QAction(tr("미리보기 창", "Preview pane"), self, checkable=True)
        self.a_preview.setChecked(self.s.get("ui/show_preview"))
        self.a_preview.toggled.connect(self._toggle_preview)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu(tr("파일(&F)", "&File"))
        m.addActions([self.a_open, self.a_new])
        self.recent_menu = m.addMenu(tr("최근 파일", "Recent"))
        m.addSeparator()
        m.addActions([self.a_close, self.a_exit])
        m = mb.addMenu(tr("편집(&E)", "&Edit"))
        m.addActions([self.a_extract, self.a_extract_sel])
        m.addSeparator()
        m.addActions([self.a_add, self.a_add_dir, self.a_rename, self.a_delete])
        m.addSeparator()
        m.addAction(self.a_search)
        m = mb.addMenu(tr("도구(&T)", "&Tools"))
        m.addActions([self.a_test, self.a_info, self.a_hash, self.a_convert, self.a_repair])
        self.enc_menu = m.addMenu(tr("파일 이름 인코딩", "File name encoding"))
        for label, codec in enc.CHOICES:
            a = self.enc_menu.addAction(label if codec != "auto" else tr("자동 감지", "Auto-detect"))
            a.triggered.connect(lambda _=False, c=codec: self.reopen_with_encoding(c))
        m.addSeparator()
        m.addAction(self.a_settings)
        m = mb.addMenu(tr("보기(&V)", "&View"))
        m.addAction(self.a_preview)
        m.addActions([self.a_up, self.a_back])
        m = mb.addMenu(tr("도움말(&H)", "&Help"))
        m.addAction(self.a_about)
        self._refresh_recent_menu()

    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(34, 34))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tb.addActions([self.a_open, self.a_new])
        tb.addSeparator()
        tb.addActions([self.a_extract, self.a_extract_sel])
        tb.addSeparator()
        tb.addActions([self.a_add, self.a_delete])
        tb.addSeparator()
        tb.addActions([self.a_test, self.a_info, self.a_hash])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("🔍 압축 파일 안에서 찾기", "🔍 Search in archive"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.setMinimumWidth(180)
        self.search.textChanged.connect(self._on_search)
        tb.addWidget(self.search)
        tb.addAction(self.a_settings)
        self.addToolBar(tb)
        self.toolbar = tb

    def _build_central(self) -> None:
        self.stack = QStackedWidget()
        self.stack.setObjectName("central")
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_browser())

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 12, 40, 24)
        self.drop = DropZone()
        self.drop.filesDropped.connect(self.handle_dropped)
        lay = QVBoxLayout(self.drop)
        lay.setContentsMargins(30, 20, 30, 24)
        lay.setSpacing(6)
        lay.addStretch(1)
        pic = QLabel()
        pic.setPixmap(icons.mascot("idle", 170))
        pic.setAlignment(Qt.AlignCenter)
        lay.addWidget(pic)
        t = QLabel(f"{APP_NAME}  {APP_NAME_KO}")
        t.setProperty("role", "title")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 30px; font-weight: 900;")
        lay.addWidget(t)
        sub = QLabel(tr("압축 파일이나 폴더를 여기로 끌어다 놓아 보세요!", "Drop an archive, file or folder here!"))
        sub.setProperty("role", "sub")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch(1)
        b1 = QPushButton(tr("  압축 파일 열기", "  Open archive"))
        b1.setIcon(icons.icon("open"))
        b1.setIconSize(QSize(24, 24))
        b1.setProperty("class", "primary big")
        b1.setProperty("class", "primary")
        b1.setMinimumHeight(46)
        b1.clicked.connect(self.act_open)
        b2 = QPushButton(tr("  새로 압축하기", "  New archive"))
        b2.setIcon(icons.icon("add"))
        b2.setIconSize(QSize(24, 24))
        b2.setMinimumHeight(46)
        b2.clicked.connect(self.act_new)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(12)
        self.recent_title = QLabel(tr("최근에 연 파일", "Recent files"))
        self.recent_title.setProperty("role", "h2")
        self.recent_title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.recent_title)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(130)
        self.recent_list.setMaximumWidth(560)
        self.recent_list.setFrameShape(QFrame.NoFrame)
        self.recent_list.itemActivated.connect(lambda it: self.open_path(Path(it.data(Qt.UserRole))))
        self.recent_list.itemClicked.connect(lambda it: self.open_path(Path(it.data(Qt.UserRole))))
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self.recent_list, 3)
        wrap.addStretch(1)
        lay.addLayout(wrap)
        lay.addStretch(1)
        outer.addWidget(self.drop)
        self._fill_recent_list()
        return page

    def _build_browser(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 4, 14, 6)
        lay.setSpacing(8)
        nav = QHBoxLayout()
        self.btn_back = QPushButton()
        self.btn_back.setIcon(icons.icon("back"))
        self.btn_back.setProperty("class", "flat")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_up = QPushButton()
        self.btn_up.setIcon(icons.icon("up"))
        self.btn_up.setProperty("class", "flat")
        self.btn_up.clicked.connect(self.go_up)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_up)
        self.crumbs = QHBoxLayout()
        self.crumbs.setSpacing(0)
        nav.addLayout(self.crumbs, 1)
        nav.addStretch(0)
        lay.addLayout(nav)
        self.split = QSplitter(Qt.Horizontal)
        self.model = ArchiveModel(self)
        self.proxy = ArchiveProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = ArchiveTable(self)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setIconSize(QSize(24, 24))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 100), (2, 100), (3, 80), (4, 150), (5, 80)):
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
            self.table.setColumnWidth(c, w)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.split.addWidget(self.table)
        self.preview = PreviewPanel()
        self.split.addWidget(self.preview)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setSizes([760, 280])
        self.preview.setVisible(self.s.get("ui/show_preview"))
        lay.addWidget(self.split, 1)
        return page

    def _build_status(self) -> None:
        sb = self.statusBar()
        self.st_left = QLabel(tr("준비됐어요!", "Ready!"))
        self.st_right = QLabel("")
        self.st_lock = QLabel()
        sb.addWidget(self.st_left, 1)
        sb.addPermanentWidget(self.st_lock)
        sb.addPermanentWidget(self.st_right)

    # ================================================================ state helpers
    def _toggle_preview(self, on: bool) -> None:
        self.preview.setVisible(on)
        self.s.set("ui/show_preview", on)

    def _update_state(self) -> None:
        has = self.reader is not None
        is_zip = has and self.reader.fmt == "zip"
        sel = bool(self.selected_nodes()) if has else False
        for a in (self.a_extract, self.a_test, self.a_info, self.a_close, self.a_convert, self.a_search):
            a.setEnabled(has)
        self.a_extract_sel.setEnabled(sel)
        for a in (self.a_add, self.a_add_dir):
            a.setEnabled(is_zip)
        self.a_delete.setEnabled(is_zip and sel)
        self.a_rename.setEnabled(is_zip and sel and len(self.selected_nodes()) == 1)
        self.a_open_file.setEnabled(sel)
        self.a_copy_path.setEnabled(sel)
        self.search.setEnabled(has)
        self.enc_menu.setEnabled(bool(has and self.reader.fmt == "zip"))
        self.a_up.setEnabled(has and bool(self.model.cwd))
        self.btn_up.setEnabled(has and bool(self.model.cwd))
        self.btn_back.setEnabled(bool(self.history))
        self.a_back.setEnabled(bool(self.history))
        if not has:
            self.setWindowTitle(f"{APP_NAME} {APP_NAME_KO}")
            self.st_left.setText(tr("준비됐어요!", "Ready!"))
            self.st_right.setText("")
            self.st_lock.clear()

    def _refresh_status(self) -> None:
        if not self.reader or not self.tree:
            return
        total = self.tree.root
        sel = self.selected_nodes()
        txt = tr(f"{len(self.model.rows):,}개 항목", f"{len(self.model.rows):,} items")
        if sel:
            txt += tr(f" · {len(sel):,}개 선택 ({human_size(sum(n.size for n in sel))})", f" · {len(sel):,} selected ({human_size(sum(n.size for n in sel))})")
        self.st_left.setText(txt)
        ratio = f" · {max(0, 1 - self.reader.packed_size / total.size) * 100:.0f}% " + tr("압축", "saved") if total.size else ""
        self.st_right.setText(tr(f"전체 {total.count:,}개 파일 · {human_size(total.size)}{ratio}",
                                 f"{total.count:,} files · {human_size(total.size)}{ratio}"))
        if self.reader.encrypted:
            self.st_lock.setPixmap(icons.pixmap("lock", 18))
            self.st_lock.setToolTip(tr("암호로 보호된 압축 파일", "Password protected"))
        else:
            self.st_lock.clear()

    def selected_nodes(self) -> List[Node]:
        if not hasattr(self, "table") or self.table.selectionModel() is None:
            return []
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return [self.model.node(r) for r in sorted(rows)]

    # ================================================================ recent files
    def _recent(self) -> List[str]:
        return [p for p in self.s.get_list("recent/files") if Path(p).exists()]

    def _fill_recent_list(self) -> None:
        self.recent_list.clear()
        items = self._recent()[:6]
        for p in items:
            it = QListWidgetItem(icons.file_icon(p, False), f"{Path(p).name}   —   {Path(p).parent}")
            it.setData(Qt.UserRole, p)
            self.recent_list.addItem(it)
        vis = bool(items)
        self.recent_list.setVisible(vis)
        self.recent_title.setVisible(vis)

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        items = self._recent()
        for p in items:
            a = self.recent_menu.addAction(Path(p).name)
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, p=p: self.open_path(Path(p)))
        self.recent_menu.setEnabled(bool(items))

    # ================================================================== opening
    def open_path(self, path: Path, encoding: Optional[str] = None, keep_cwd: str = "") -> bool:
        path = Path(path)
        if not path.exists():
            message(self, "error", tr("파일을 찾을 수 없어요", "File not found"), str(path))
            return False
        self.preview.wait()
        reader = self.actions.open_reader(self, path, encoding)
        if reader is None:
            return False
        self.close_archive()
        self.reader = reader
        self.tree = ArchiveTree(reader.entries)
        self.model.set_tree(self.tree)
        self.history.clear()
        if keep_cwd and keep_cwd in self.tree.by_path:
            self.model.cd(keep_cwd)
        self.stack.setCurrentIndex(1)
        self.setWindowTitle(f"{path.name} - {APP_NAME}")
        self.s.push_recent("recent/files", str(path))
        self._refresh_recent_menu()
        self._fill_recent_list()
        self._rebuild_crumbs()
        self._update_state()
        self._refresh_status()
        self.preview.clear()
        self.table.setFocus()
        if reader.detected_encoding and reader.detected_encoding not in ("utf-8", "cp437"):
            self.statusBar().showMessage(tr(f"파일 이름 인코딩을 {reader.detected_encoding.upper()}(으)로 자동 인식했어요", f"File names decoded as {reader.detected_encoding.upper()}"), 6000)
        return True

    def close_archive(self) -> None:
        self.preview.wait()
        if self.reader:
            self.reader.close()
        self.reader = None
        self.tree = None
        self.model.set_tree(None)
        self.history.clear()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.stack.setCurrentIndex(0)
        self._update_state()

    def reopen_with_encoding(self, codec: str) -> None:
        if self.reader:
            self.open_path(self.reader.path, None if codec == "auto" else codec, self.model.cwd)

    def reload(self) -> None:
        if self.reader:
            self.open_path(self.reader.path, keep_cwd=self.model.cwd)

    # ================================================================== navigation
    def _rebuild_crumbs(self) -> None:
        while self.crumbs.count():
            w = self.crumbs.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not self.reader:
            return
        parts = [("", self.reader.path.name)]
        cur = ""
        for p in [x for x in self.model.cwd.split("/") if x]:
            cur = f"{cur}/{p}" if cur else p
            parts.append((cur, p))
        for i, (path, label) in enumerate(parts):
            b = QPushButton(label)
            b.setProperty("class", "flat")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=path: self.cd(p))
            self.crumbs.addWidget(b)
            if i < len(parts) - 1:
                sep = QLabel("›")
                sep.setProperty("role", "sub")
                self.crumbs.addWidget(sep)
        self.crumbs.addStretch(1)

    def cd(self, path: str, push: bool = True) -> None:
        if not self.reader or path == self.model.cwd and not self.model.query:
            return
        if push:
            self.history.append(self.model.cwd)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.model.cd(path)
        self.table.sortByColumn(self.proxy.sortColumn(), self.proxy.sortOrder())
        self._rebuild_crumbs()
        self.preview.clear()
        self._update_state()
        self._refresh_status()

    def go_up(self) -> None:
        if self.reader and self.model.cwd:
            self.cd(self.model.cwd.rsplit("/", 1)[0] if "/" in self.model.cwd else "")

    def go_back(self) -> None:
        if self.history:
            self.cd(self.history.pop(), push=False)

    def _on_search(self, text: str) -> None:
        if not self.reader:
            return
        self.model.search(text)
        self._refresh_status()

    def _on_double_click(self, idx: QModelIndex) -> None:
        n = self.model.node(self.proxy.mapToSource(idx).row())
        if n.is_dir:
            self.cd(n.path)
        else:
            self.act_open_selected()

    def _on_selection(self, *_a) -> None:
        sel = self.selected_nodes()
        self._update_state()
        self._refresh_status()
        if len(sel) == 1 and self.reader and self.preview.isVisible():
            n = sel[0]
            locked = n.encrypted and not self.reader.password
            self.preview.show_node(n, self.reader, locked=locked)
        elif not sel:
            self.preview.clear()
        else:
            self.preview.clear(tr(f"{len(sel):,}개 선택됨", f"{len(sel):,} selected"))

    def _context_menu(self, pos) -> None:
        if not self.reader:
            return
        m = QMenu(self)
        if self.selected_nodes():
            m.addAction(self.a_open_file)
            m.addAction(self.a_extract_sel)
            m.addSeparator()
            m.addAction(self.a_copy_path)
            if self.reader.fmt == "zip":
                m.addAction(self.a_rename)
                m.addAction(self.a_delete)
        else:
            m.addAction(self.a_extract)
            if self.reader.fmt == "zip":
                m.addAction(self.a_add)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ================================================================== actions
    def act_open(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, tr("압축 파일 열기", "Open archive"), self.s.get("recent/last_dir", "") or str(Path.home()),
                                          tr("모든 파일 (*.*)", "All files (*.*)"))
        if f:
            self.s.set("recent/last_dir", str(Path(f).parent))
            self.open_path(Path(f))

    def act_new(self) -> None:
        if self.reader:
            m = QMenu(self)
            m.addAction(tr("새 압축 파일 만들기 (파일 선택)…", "New archive from files…"), self._pick_and_compress_files)
            m.addAction(tr("새 압축 파일 만들기 (폴더 선택)…", "New archive from folder…"), self._pick_and_compress_folder)
            m.exec(self.cursor().pos())
            return
        m = QMenu(self)
        m.addAction(icons.icon("add_file"), tr("파일 선택…", "Choose files…"), self._pick_and_compress_files)
        m.addAction(icons.icon("add_folder"), tr("폴더 선택…", "Choose folder…"), self._pick_and_compress_folder)
        m.exec(self.cursor().pos())

    def _pick_and_compress_files(self) -> None:
        fs, _ = QFileDialog.getOpenFileNames(self, tr("압축할 파일 선택", "Choose files to compress"))
        if fs:
            self.compress_paths([Path(f) for f in fs])

    def _pick_and_compress_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("압축할 폴더 선택", "Choose folder to compress"))
        if d:
            self.compress_paths([Path(d)])

    def compress_paths(self, paths: List[Path]) -> None:
        self.preview.wait()
        res = self.actions.compress_dialog(self, paths)
        if res and res.outputs and self.s.get("compress/delete_sources"):
            pass  # handled inside engine through recycle bin when enabled

    def act_extract_all(self) -> None:
        if self.reader:
            self.preview.wait()
            out = self.actions.extract(self, self.reader)
            self._after_extract(out)

    def act_extract_selected(self) -> None:
        nodes = self.selected_nodes()
        if not (self.reader and nodes):
            return
        self.preview.wait()
        entries = self.tree.entries_for(nodes)
        out = self.actions.extract(self, self.reader, entries, strip_prefix=self.model.cwd,
                                   selected=len(nodes),
                                   opts=ExtractOptions(folder_mode="never", overwrite=self.s.get("extract/overwrite"),
                                                       propagate_motw=self.s.get("extract/motw")))
        self._after_extract(out)

    def _after_extract(self, out) -> None:
        if out and out.reader_closed:
            self.close_archive()

    def act_open_selected(self) -> None:
        nodes = self.selected_nodes()
        if not (self.reader and nodes):
            return
        n = nodes[0]
        if n.is_dir:
            self.cd(n.path)
        elif n.entry:
            self.preview.wait()
            self.actions.open_member(self, self.reader, n.entry)

    def act_test(self) -> None:
        if self.reader:
            self.preview.wait()
            self.actions.test(self, self.reader)

    def act_info(self) -> None:
        if not self.reader:
            return
        r = self.reader
        st = analyze(r)
        methods = sorted({e.method for e in r.entries if e.method and not e.is_dir})
        rows = [
            (tr("파일", "File"), str(r.path)),
            (tr("형식", "Format"), r.fmt.upper()),
            (tr("압축 파일 크기", "Archive size"), human_size(r.packed_size)),
            (tr("원본 크기", "Original size"), human_size(st.total_size)),
            (tr("압축률", "Saved"), f"{st.ratio * 100:.1f}%"),
            (tr("파일 / 폴더", "Files / folders"), f"{st.files:,} / {st.dirs:,}"),
            (tr("암호화", "Encrypted"), tr("예 (AES)", "Yes") if r.encrypted else tr("아니요", "No")),
            (tr("압축 방식", "Method"), ", ".join(methods) or "-"),
        ]
        if r.detected_encoding:
            rows.append((tr("이름 인코딩", "Name encoding"), r.detected_encoding.upper()))
        InfoDialog(self, rows, tr("압축 파일 정보", "Archive info"), r.path.name, r.comment).exec()

    def act_hash(self) -> None:
        HashDialog(self, str(self.reader.path) if self.reader else "").exec()

    def act_convert(self) -> None:
        if self.reader:
            self.preview.wait()
            self.actions.convert(self, self.reader)

    def act_repair(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, tr("복구할 ZIP 선택", "Choose a damaged ZIP"), "", "ZIP (*.zip);;*.*")
        if f:
            fixed = self.actions.repair(self, Path(f))
            if fixed:
                self.open_path(fixed)

    def act_settings(self) -> None:
        d = SettingsDialog(self, self.s)
        if d.exec() and d.changed_ui:
            self.settings_changed.emit()

    def act_about(self) -> None:
        AboutDialog(self).exec()

    def act_copy_path(self) -> None:
        nodes = self.selected_nodes()
        if nodes:
            QGuiApplication.clipboard().setText("\n".join(n.path for n in nodes))

    # ---- zip editing ------------------------------------------------------------------------------------
    def act_add_files(self) -> None:
        fs, _ = QFileDialog.getOpenFileNames(self, tr("추가할 파일", "Files to add"))
        if fs:
            self._add_paths([Path(f) for f in fs])

    def act_add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("추가할 폴더", "Folder to add"))
        if d:
            self._add_paths([Path(d)])

    def _add_paths(self, paths: List[Path]) -> None:
        if not self.reader:
            return
        self.preview.wait()
        cwd = self.model.cwd
        if self.actions.edit_zip(self, self.reader, tr("압축 파일에 추가하는 중", "Adding to archive"), add=paths, add_prefix=cwd):
            self.reload()
        else:
            self.reload()

    def act_delete(self) -> None:
        nodes = self.selected_nodes()
        if not (self.reader and nodes):
            return
        if not confirm(self, tr("삭제할까요?", "Delete?"),
                       tr(f"선택한 {len(nodes):,}개 항목을 압축 파일에서 지워요.\n되돌릴 수 없어요.", f"Remove {len(nodes):,} items from the archive.\nThis can't be undone."),
                       tr("삭제", "Delete"), danger=True):
            return
        self.preview.wait()
        self.actions.edit_zip(self, self.reader, tr("삭제하는 중", "Deleting"), remove=[n.path for n in nodes])
        self.reload()

    def act_rename(self) -> None:
        nodes = self.selected_nodes()
        if not (self.reader and len(nodes) == 1):
            return
        n = nodes[0]
        new, ok = QInputDialog.getText(self, tr("이름 바꾸기", "Rename"), tr("새 이름", "New name"), text=n.name)
        if not ok or not new.strip() or new == n.name or "/" in new or "\\" in new:
            return
        parent = n.path.rsplit("/", 1)[0] + "/" if "/" in n.path else ""
        self.preview.wait()
        self.actions.edit_zip(self, self.reader, tr("이름 바꾸는 중", "Renaming"), rename={n.path: parent + new.strip()})
        self.reload()

    # ================================================================== drag & drop
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.handle_dropped(paths)

    def handle_dropped(self, paths: List[str]) -> None:
        ps = [Path(p) for p in paths]
        if len(ps) == 1 and ps[0].is_file() and sniff_path(ps[0]) is not None:
            if not self.reader or self.reader.path != ps[0]:
                if self.reader and self.reader.fmt == "zip":
                    i = message(self, "ask", tr("어떻게 할까요?", "What to do?"),
                                tr(f"'{ps[0].name}'은(는) 압축 파일이에요.", f"'{ps[0].name}' is an archive."),
                                buttons=[(tr("취소", "Cancel"), "normal"), (tr("현재 압축 파일에 추가", "Add to current"), "normal"),
                                         (tr("새로 열기", "Open it"), "primary")])
                    if i == 1:
                        self._add_paths(ps)
                    elif i == 2:
                        self.open_path(ps[0])
                    return
                self.open_path(ps[0])
            return
        if self.reader and self.reader.fmt == "zip":
            i = message(self, "ask", tr("어떻게 할까요?", "What to do?"),
                        tr(f"{len(ps)}개 항목을 어디에 둘까요?", f"What to do with {len(ps)} items?"),
                        buttons=[(tr("취소", "Cancel"), "normal"), (tr("새로 압축하기", "New archive"), "normal"),
                                 (tr("현재 압축 파일에 추가", "Add to current"), "primary")])
            if i == 2:
                self._add_paths(ps)
            elif i == 1:
                self.compress_paths(ps)
            return
        self.compress_paths(ps)

    # ---- drag-out ---------------------------------------------------------------------------------------------
    def stage_selection_for_drag(self) -> List[QUrl]:
        nodes = self.selected_nodes()
        if not (self.reader and nodes):
            return []
        if self.reader.encrypted and not self.actions.ensure_password(self, self.reader):
            return []
        entries = self.tree.entries_for(nodes)
        if sum(e.size for e in entries) > 300 * 1024 * 1024:
            message(self, "info", tr("파일이 너무 커요", "Too large to drag"), tr("300MB가 넘는 항목은 '선택 풀기'를 사용해 주세요.", "Use 'Extract selected' for items above 300 MB."))
            return []
        tmp = Path(tempfile.mkdtemp(prefix="warpzip-drag-"))
        self._drag_dirs.append(tmp)
        self.preview.wait()
        opts = ExtractOptions(folder_mode="never", overwrite="overwrite", strip_prefix=self.model.cwd, propagate_motw=False)
        out = run_job(self, tr("꺼내는 중", "Extracting"), self.reader.path.name,
                      lambda cb, cancel: ar.extract(self.reader, tmp, entries, opts, cb, cancel), auto_close=True)
        if not out.ok:
            return []
        tops = []
        for n in nodes:
            p = tmp / n.name
            if p.exists():
                tops.append(QUrl.fromLocalFile(str(p)))
        return tops

    # ================================================================== lifecycle
    def closeEvent(self, e) -> None:
        self.preview.wait()
        self.s.set("ui/geometry", self.saveGeometry())
        if self.reader:
            self.reader.close()
        self.actions.cleanup()
        for d in self._drag_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self.s.sync()
        super().closeEvent(e)

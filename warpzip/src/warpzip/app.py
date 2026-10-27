"""GUI bootstrap: single instance, argument dispatch, theme/language handling."""
from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import APP_NAME, ORG_NAME, __version__
from .core.formats import sniff_path
from .settings import Settings
from .ui import icons, theme
from .ui.actions import Actions
from .ui.i18n import set_language
from .ui.main_window import MainWindow

SERVER_NAME = f"WarpZip-{getpass.getuser()}-single"
AGGREGATE_MS = 450

GUI_FLAGS = {"--compress", "--quick-zip", "--quick-7z", "--extract", "--extract-here", "--extract-folder", "--open"}


def forward_to_running(argv: List[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(500):
        return False
    sock.write(json.dumps(argv).encode("utf-8") + b"\n")
    sock.flush()
    sock.waitForBytesWritten(2000)
    sock.waitForReadyRead(2000)          # wait for the ack so the pipe is not closed under unread data
    sock.disconnectFromServer()
    return True


class SingleInstance(QObject):
    received = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_conn)
        if not self.server.listen(SERVER_NAME):
            QLocalServer.removeServer(SERVER_NAME)
            self.server.listen(SERVER_NAME)

    def _on_conn(self) -> None:
        # Fully asynchronous: never block the GUI thread waiting on the pipe (unreliable on Windows).
        while True:
            sock = self.server.nextPendingConnection()
            if sock is None:
                return
            buf = bytearray()

            def on_ready(sock=sock, buf=buf) -> None:
                buf.extend(bytes(sock.readAll()))
                if b"\n" not in buf:
                    return
                sock.readyRead.disconnect()
                try:
                    argv = json.loads(bytes(buf).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    argv = None
                sock.write(b"1")             # ack: lets the sender close the pipe safely
                sock.flush()
                sock.disconnectFromServer()
                if isinstance(argv, list):
                    self.received.emit(argv)

            sock.readyRead.connect(on_ready)
            sock.disconnected.connect(sock.deleteLater)
            if sock.bytesAvailable():
                on_ready()


class WarpApp(QObject):
    def __init__(self, app: QApplication, settings: Settings) -> None:
        super().__init__()
        self.app = app
        self.s = settings
        self.actions = Actions(settings)
        self.window: Optional[MainWindow] = None
        self.pending: Dict[str, List[str]] = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._flush)
        self._busy = False
        self.build_window()

    # ---- window lifecycle -------------------------------------------------------------------
    def apply_look(self) -> None:
        set_language(self.s.get("language"))
        icons.clear_cache()
        theme.apply(self.app, self.s.get("theme"))

    def build_window(self, reopen: Optional[Path] = None, cwd: str = "") -> None:
        self.apply_look()
        self.window = MainWindow(self.s, self.actions)
        self.window.settings_changed.connect(self.rebuild_window)
        if reopen:
            self.window.show()
            self.window.open_path(reopen, keep_cwd=cwd)

    def rebuild_window(self) -> None:
        old = self.window
        path = old.reader.path if old and old.reader else None
        cwd = old.model.cwd if old and old.reader else ""
        if old:
            old.settings_changed.disconnect()
            old.close()
        self.build_window(path, cwd)
        if not path:
            self.window.show()

    # ---- command dispatch -------------------------------------------------------------------------
    def handle_args(self, argv: List[str]) -> None:
        argv = [a for a in argv if a]
        if not argv:
            self.show_main()
            return
        flag = argv[0] if argv[0] in GUI_FLAGS else ""
        paths = argv[1:] if flag else argv
        if flag in ("--compress", "--quick-zip", "--quick-7z", "--extract", "--extract-here", "--extract-folder"):
            self.pending.setdefault(flag, []).extend(paths)
            self.timer.start(AGGREGATE_MS)
            return
        # plain paths: open the first archive; otherwise offer to compress
        first = Path(paths[0])
        if len(paths) == 1 and first.is_file() and (sniff_path(first) or first.suffix.lower() == ".001"):
            self.show_main()
            self.window.open_path(first)
        else:
            self.show_main()
            self.window.compress_paths([Path(p) for p in paths])

    def show_main(self) -> None:
        w = self.window
        w.show()
        w.setWindowState(w.windowState() & ~Qt.WindowMinimized)
        w.raise_()
        w.activateWindow()

    def _flush(self) -> None:
        if self._busy:
            self.timer.start(AGGREGATE_MS)
            return
        self._busy = True
        try:
            parent = self.window if self.window.isVisible() else None
            for flag, paths in list(self.pending.items()):
                del self.pending[flag]
                ps = [Path(p) for p in dict.fromkeys(paths)]
                if flag == "--compress":
                    self.actions.compress_dialog(parent, ps)
                elif flag == "--quick-zip":
                    self.actions.quick_compress(parent, ps, "zip")
                elif flag == "--quick-7z":
                    self.actions.quick_compress(parent, ps, "7z")
                elif flag == "--extract":
                    self.actions.quick_extract(parent, ps, "ask")
                elif flag == "--extract-here":
                    self.actions.quick_extract(parent, ps, "here")
                elif flag == "--extract-folder":
                    self.actions.quick_extract(parent, ps, "folder")
        finally:
            self._busy = False
        if not self.pending and not self.window.isVisible():
            self.app.quit()


def _set_app_id() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WarpZip.WarpZip.1")
        except Exception:  # noqa: BLE001
            pass


def run_gui(argv: List[str]) -> int:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false;qt.qpa.fonts=false")
    _set_app_id()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    if forward_to_running(argv):
        return 0
    settings = Settings()
    single = SingleInstance()
    warp = WarpApp(app, settings)
    single.received.connect(warp.handle_args)
    app.setWindowIcon(icons.app_icon())
    app.lastWindowClosed.connect(lambda: None)
    warp.handle_args(argv)
    # closing the main window (when not busy with a quick action) ends the program
    def maybe_quit() -> None:
        if warp.window and not warp.window.isVisible() and not warp.pending and not warp._busy:
            app.quit()
    app.lastWindowClosed.connect(lambda: QTimer.singleShot(200, maybe_quit))
    code = app.exec()
    settings.sync()
    return code

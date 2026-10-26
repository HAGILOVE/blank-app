"""Side panel that previews the selected archive member."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QVBoxLayout

from ..core.entry import Entry
from ..core.fsutil import human_size
from . import icons
from .archive_model import Node
from .i18n import tr

TEXT_EXT = {"txt", "md", "log", "ini", "cfg", "conf", "json", "xml", "yaml", "yml", "csv", "tsv", "py", "js", "ts",
            "html", "htm", "css", "c", "h", "cpp", "hpp", "cs", "java", "go", "rs", "rb", "php", "sh", "bat",
            "ps1", "sql", "lua", "kt", "srt", "nfo", "toml", "gitignore", "license", "readme"}
IMG_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "ico", "svg"}
MAX_PREVIEW = 6 * 1024 * 1024


class LoadThread(QThread):
    loaded = Signal(int, str, object)

    def __init__(self, token: int, reader, entry: Entry, kind: str) -> None:
        super().__init__()
        self.token, self.reader, self.entry, self.kind = token, reader, entry, kind

    def run(self) -> None:
        try:
            with self.reader.open_member(self.entry) as f:
                data = f.read(MAX_PREVIEW if self.kind == "image" else 96 * 1024)
            self.loaded.emit(self.token, self.kind, data)
        except Exception as ex:  # noqa: BLE001
            self.loaded.emit(self.token, "error", str(ex))


class PreviewPanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setMinimumWidth(240)
        self._token = 0
        self._thread: Optional[LoadThread] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setMinimumHeight(150)
        lay.addWidget(self.pic)
        self.title = QLabel("")
        self.title.setProperty("role", "h2")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)
        self.meta = QLabel("")
        self.meta.setProperty("role", "sub")
        self.meta.setAlignment(Qt.AlignCenter)
        self.meta.setWordWrap(True)
        lay.addWidget(self.meta)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setVisible(False)
        self.text.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 12px;")
        lay.addWidget(self.text, 1)
        lay.addStretch(0)
        self.clear()

    def wait(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.wait(3000)

    def clear(self, msg: str = "") -> None:
        self._token += 1
        self.pic.setPixmap(icons.mascot("sleep", 120))
        self.title.setText(msg or tr("파일을 선택하면 미리 볼 수 있어요", "Select a file to preview"))
        self.meta.setText("")
        self.text.setVisible(False)

    def show_node(self, node: Node, reader, count: int = 0, locked: bool = False) -> None:
        self._token += 1
        tok = self._token
        self.title.setText(node.name)
        self.text.setVisible(False)
        self.pic.setPixmap(icons.file_pixmap(node.name, node.is_dir, 88))
        if node.is_dir:
            self.meta.setText(tr(f"폴더 · 파일 {node.count:,}개 · {human_size(node.size)}", f"Folder · {node.count:,} files · {human_size(node.size)}"))
            return
        when = node.mtime.strftime("%Y-%m-%d %H:%M") if node.mtime else ""
        self.meta.setText(f"{human_size(node.size)}  ·  {when}")
        if node.entry is None or reader is None or locked:
            if locked:
                self.pic.setPixmap(icons.pixmap("lock", 88))
                self.meta.setText(self.meta.text() + "\n" + tr("암호가 필요해요", "Password required"))
            return
        ext = node.name.rsplit(".", 1)[-1].lower() if "." in node.name else node.name.lower()
        kind = "image" if ext in IMG_EXT else "text" if ext in TEXT_EXT else ""
        if not kind or node.size > MAX_PREVIEW:
            return
        self.wait()
        self._thread = LoadThread(tok, reader, node.entry, kind)
        self._thread.loaded.connect(self._loaded)
        self._thread.start()

    def _loaded(self, token: int, kind: str, data) -> None:
        if token != self._token:
            return
        if kind == "image":
            pm = QPixmap()
            if pm.loadFromData(data):
                self.pic.setPixmap(pm.scaled(self.width() - 40, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif kind == "text":
            if b"\x00" in data[:2048]:
                return
            for codec in ("utf-8-sig", "cp949", "latin-1"):
                try:
                    txt = data.decode(codec)
                    break
                except UnicodeDecodeError:
                    continue
            self.text.setPlainText(txt[:20000])
            self.text.setVisible(True)

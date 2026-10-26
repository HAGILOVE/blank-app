"""Persistent user settings (QSettings INI; portable when 'portable.flag' sits next to the exe)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List

from PySide6.QtCore import QSettings

DEFAULTS = {
    "language": "auto",            # auto | ko | en
    "theme": "auto",               # auto | light | dark
    "compress/format": "zip",
    "compress/level": 5,
    "compress/zip_method": "deflate",
    "compress/smart_store": True,
    "compress/exclude": "Thumbs.db;desktop.ini;.DS_Store;__MACOSX;~$*",
    "compress/delete_sources": False,
    "compress/encrypt_names": True,
    "extract/folder_mode": "smart",
    "extract/overwrite": "rename",
    "extract/open_folder": True,
    "extract/delete_archive": False,
    "extract/motw": True,
    "extract/dest_mode": "same",   # same | last
    "extract/last_dest": "",
    "ui/auto_close_progress": False,
    "ui/show_preview": True,
    "ui/remember_passwords": False,
    "ui/geometry": None,
    "ui/column_widths": "",
    "ui/first_run_done": False,
    "ui/sounds": False,
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def is_portable() -> bool:
    return (app_dir() / "portable.flag").exists()


class Settings:
    def __init__(self, path: str | None = None) -> None:
        if path is None:
            if is_portable():
                path = str(app_dir() / "warpzip.ini")
            else:
                base = os.environ.get("APPDATA") or str(Path.home() / ".config")
                d = Path(base) / "WarpZip"
                d.mkdir(parents=True, exist_ok=True)
                path = str(d / "warpzip.ini")
        self.q = QSettings(path, QSettings.IniFormat)
        self.q.setIniCodec = None  # Qt6 INI is UTF-8 already

    def get(self, key: str, default: Any = None) -> Any:
        d = DEFAULTS.get(key) if default is None else default
        v = self.q.value(key, d)
        if isinstance(d, bool):
            return v in (True, "true", "1", 1)
        if isinstance(d, int) and not isinstance(d, bool):
            try:
                return int(v)
            except (TypeError, ValueError):
                return d
        return v

    def set(self, key: str, value: Any) -> None:
        self.q.setValue(key, value)

    def get_list(self, key: str) -> List[str]:
        v = self.q.value(key, [])
        if isinstance(v, str):
            return [v] if v else []
        return [str(x) for x in (v or [])]

    def push_recent(self, key: str, value: str, limit: int = 12) -> None:
        items = [x for x in self.get_list(key) if x != value]
        items.insert(0, value)
        self.q.setValue(key, items[:limit])

    def remove_recent(self, key: str, value: str) -> None:
        self.q.setValue(key, [x for x in self.get_list(key) if x != value])

    def sync(self) -> None:
        self.q.sync()

"""Icon / mascot loading with theme-aware outline colour and a pixmap cache."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

ASSETS = Path(__file__).resolve().parents[1] / "assets"
_INK = "#3B2A6B"
_ext_map: Optional[dict] = None


def asset_path(*parts: str) -> Path:
    return ASSETS.joinpath(*parts)


@lru_cache(maxsize=None)
def _svg_text(rel: str) -> str:
    return (ASSETS / rel).read_text(encoding="utf-8")


def _render(svg: str, w: int, h: int, dpr: float) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(int(w * dpr), int(h * dpr), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    r.render(p)
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


@lru_cache(maxsize=None)
def _pixmap(rel: str, size: int, ink: str, dpr: float) -> QPixmap:
    svg = _svg_text(rel).replace(_INK, ink)
    return _render(svg, size, size, dpr)


def pixmap(name: str, size: int = 24, themed: bool = True, dpr: float = 2.0) -> QPixmap:
    ink = theme.current().ink if themed else _INK
    return _pixmap(f"icons/{name}.svg", size, ink, dpr)


def icon(name: str) -> QIcon:
    ic = QIcon()
    for s in (16, 20, 24, 32, 48):
        pm = pixmap(name, s)
        ic.addPixmap(pm, QIcon.Normal)
        ic.addPixmap(pm, QIcon.Selected)
    return ic


def _ext_icon_name(ext: str) -> str:
    global _ext_map
    if _ext_map is None:
        _ext_map = json.loads((ASSETS / "ext_icons.json").read_text(encoding="utf-8"))
    return _ext_map.get(ext.lower().lstrip("."), "f_file")


def file_icon(name: str, is_dir: bool = False) -> QIcon:
    return icon("folder" if is_dir else _ext_icon_name(name.rsplit(".", 1)[-1] if "." in name else ""))


def file_pixmap(name: str, is_dir: bool, size: int) -> QPixmap:
    return pixmap("folder" if is_dir else _ext_icon_name(name.rsplit(".", 1)[-1] if "." in name else ""), size)


def mascot(mood: str = "idle", size: int = 160) -> QPixmap:
    return _pixmap(f"mascot/warpy_{mood}.svg", size, _INK, 2.0)


def app_icon() -> QIcon:
    ic = QIcon(str(ASSETS / "app.ico"))
    if ic.isNull():
        ic = QIcon(_pixmap("app_icon.svg", 256, _INK, 1.0))
    return ic


def clear_cache() -> None:
    _pixmap.cache_clear()

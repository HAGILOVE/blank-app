"""SVG -> PNG rendering helpers (Qt based, headless)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

_app = None


def ensure_app():
    global _app
    if _app is None:
        _app = QGuiApplication.instance() or QGuiApplication([])
    return _app


def render(svg: str, size: int, bg: str | None = None) -> QImage:
    ensure_app()
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(bg) if bg else Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    r.render(p)
    p.end()
    return img

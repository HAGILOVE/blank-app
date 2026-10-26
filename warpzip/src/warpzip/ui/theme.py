"""Light / dark palettes and the global stylesheet."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface2: str
    text: str
    subtext: str
    border: str
    primary: str
    primary_h: str
    on_primary: str
    select: str
    ink: str          # outline colour injected into SVG icons
    danger: str = "#FF6B81"
    ok: str = "#35C98B"
    pink: str = "#FF8FB8"
    mint: str = "#5EEAD4"


LIGHT = Palette("light", "#F7F5FF", "#FFFFFF", "#F0ECFF", "#2B2150", "#7A70A8", "#E2DBFF",
                "#7C5CFF", "#6A48F2", "#FFFFFF", "#E7E0FF", "#3B2A6B")
DARK = Palette("dark", "#17142A", "#211D3A", "#2B2650", "#ECE8FF", "#A59DD0", "#383160",
               "#9D86FF", "#B19DFF", "#17142A", "#3B3478", "#CFC4FF")

_current = LIGHT


def current() -> Palette:
    return _current


def resolve(mode: str, app: QApplication) -> Palette:
    if mode == "dark":
        return DARK
    if mode == "light":
        return LIGHT
    try:
        from PySide6.QtCore import Qt
        return DARK if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT
    except Exception:  # noqa: BLE001
        return LIGHT


def _indicators(p: Palette) -> dict:
    """Draw checkbox / radio indicator PNGs (QSS cannot paint them itself)."""
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen

    d = Path(tempfile.gettempdir()) / f"warpzip-ui-{p.name}"
    d.mkdir(exist_ok=True)
    out = {}
    S = 40  # drawn at 2x for crisp edges (displayed at 20px)
    for kind in ("check", "radio"):
        for state in ("off", "on", "off_h", "dis"):
            img = QImage(S, S, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            q = QPainter(img)
            q.setRenderHint(QPainter.Antialiasing)
            on = state == "on"
            border = QColor(p.primary if state in ("on", "off_h") else p.border)
            fill = QColor(p.primary) if on else QColor(p.surface)
            if state == "dis":
                border, fill = QColor(p.border), QColor(p.surface2)
            q.setPen(QPen(border, 3))
            q.setBrush(fill)
            r = QRectF(3, 3, S - 6, S - 6)
            if kind == "check":
                q.drawRoundedRect(r, 9, 9)
            else:
                q.drawEllipse(r)
            if on:
                q.setPen(QPen(QColor(p.on_primary), 4.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                if kind == "check":
                    q.drawPolyline([QPointF(11, 21), QPointF(17.5, 27.5), QPointF(29, 13.5)])
                else:
                    q.setPen(Qt.NoPen)
                    q.setBrush(QColor(p.on_primary))
                    q.drawEllipse(QRectF(12.5, 12.5, 15, 15))
            q.end()
            f = d / f"{kind}_{state}.png"
            img.save(str(f))
            out[f"{kind}_{state}"] = f.as_posix()
    return out


def stylesheet(p: Palette) -> str:
    ind = _indicators(p)
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QWidget#central, QStackedWidget {{ background: {p.bg}; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 800; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 700; }}
QLabel[role="sub"] {{ color: {p.subtext}; }}
QLabel[role="hint"] {{ color: {p.subtext}; font-size: 11px; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 4px 8px; border-radius: 6px; }}

QMenuBar {{ background: {p.bg}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 8px; background: transparent; }}
QMenuBar::item:selected {{ background: {p.select}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 7px; }}
QMenu::item:selected {{ background: {p.select}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}

QToolBar {{ background: {p.bg}; border: none; spacing: 4px; padding: 4px 8px; }}
QToolBar QToolButton {{ background: transparent; border-radius: 12px; padding: 6px 8px; margin: 0 1px;
    min-width: 58px; font-weight: 600; }}
QToolBar QToolButton:hover {{ background: {p.select}; }}
QToolBar QToolButton:pressed {{ background: {p.border}; }}
QToolBar QToolButton:disabled {{ color: {p.subtext}; }}
QToolBar::separator {{ width: 1px; background: {p.border}; margin: 8px 6px; }}

QPushButton {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 12px; padding: 7px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {p.surface2}; border-color: {p.primary}; }}
QPushButton:pressed {{ background: {p.select}; }}
QPushButton:disabled {{ color: {p.subtext}; background: {p.surface2}; border-color: {p.border}; }}
QPushButton[class="primary"] {{ background: {p.primary}; color: {p.on_primary}; border: 1.5px solid {p.primary}; }}
QPushButton[class="primary"]:hover {{ background: {p.primary_h}; border-color: {p.primary_h}; }}
QPushButton[class="primary"]:disabled {{ background: {p.border}; color: {p.subtext}; border-color: {p.border}; }}
QPushButton[class="danger"] {{ color: {p.danger}; }}
QPushButton[class="flat"] {{ border: none; background: transparent; padding: 5px 10px; }}
QPushButton[class="flat"]:hover {{ background: {p.select}; }}
QPushButton[class="big"] {{ padding: 12px 24px; font-size: 14px; border-radius: 16px; }}

QToolButton[class="chip"] {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 12px; padding: 7px 14px; font-weight: 700; }}
QToolButton[class="chip"]:hover {{ border-color: {p.primary}; }}
QToolButton[class="chip"]:checked {{ background: {p.primary}; color: {p.on_primary}; border-color: {p.primary}; }}
QToolButton[class="chip"]:disabled {{ color: {p.subtext}; background: {p.surface2}; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 10px;
    padding: 6px 10px; selection-background-color: {p.primary}; selection-color: {p.on_primary}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {p.primary}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {p.subtext}; background: {p.surface2}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; selection-background-color: {p.select}; selection-color: {p.text}; padding: 4px; outline: 0; }}

QGroupBox {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 14px; margin-top: 16px; padding: 14px 12px 10px 12px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {p.subtext}; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; }}
QCheckBox::indicator:unchecked {{ image: url({ind["check_off"]}); }}
QCheckBox::indicator:unchecked:hover {{ image: url({ind["check_off_h"]}); }}
QCheckBox::indicator:checked {{ image: url({ind["check_on"]}); }}
QCheckBox::indicator:disabled {{ image: url({ind["check_dis"]}); }}
QRadioButton::indicator:unchecked {{ image: url({ind["radio_off"]}); }}
QRadioButton::indicator:unchecked:hover {{ image: url({ind["radio_off_h"]}); }}
QRadioButton::indicator:checked {{ image: url({ind["radio_on"]}); }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QTableView, QListWidget, QTreeView {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 14px; gridline-color: transparent;
    alternate-background-color: {p.surface2}; selection-background-color: {p.select}; selection-color: {p.text}; padding: 4px; }}
QTableView::item, QListWidget::item {{ padding: 4px 6px; border-radius: 8px; }}
QTableView::item:selected, QListWidget::item:selected {{ background: {p.select}; color: {p.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {p.subtext}; border: none; border-bottom: 1.5px solid {p.border}; padding: 6px 8px; font-weight: 700; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {p.primary}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {p.bg}; color: {p.subtext}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: transparent; width: 8px; }}
QTabWidget::pane {{ border: 1.5px solid {p.border}; border-radius: 12px; background: {p.surface}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; border-radius: 10px; margin: 2px; font-weight: 600; }}
QTabBar::tab:selected {{ background: {p.select}; }}
QFrame[role="card"] {{ background: {p.surface}; border: 1.5px solid {p.border}; border-radius: 18px; }}
QFrame[role="drop"] {{ background: {p.surface}; border: 2.5px dashed {p.border}; border-radius: 24px; }}
QFrame[role="drop"][hot="true"] {{ border-color: {p.primary}; background: {p.select}; }}
"""


def apply(app: QApplication, mode: str) -> Palette:
    global _current
    p = resolve(mode, app)
    _current = p
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p.bg))
    pal.setColor(QPalette.WindowText, QColor(p.text))
    pal.setColor(QPalette.Base, QColor(p.surface))
    pal.setColor(QPalette.AlternateBase, QColor(p.surface2))
    pal.setColor(QPalette.Text, QColor(p.text))
    pal.setColor(QPalette.Button, QColor(p.surface))
    pal.setColor(QPalette.ButtonText, QColor(p.text))
    pal.setColor(QPalette.Highlight, QColor(p.primary))
    pal.setColor(QPalette.HighlightedText, QColor(p.on_primary))
    pal.setColor(QPalette.ToolTipBase, QColor(p.surface))
    pal.setColor(QPalette.ToolTipText, QColor(p.text))
    pal.setColor(QPalette.PlaceholderText, QColor(p.subtext))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p.subtext))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p.subtext))
    app.setPalette(pal)
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo",
                   "Noto Sans CJK KR", "Noto Sans KR", "sans-serif"])
    f.setPointSize(10)
    app.setFont(f)
    app.setStyleSheet(stylesheet(p))
    return p

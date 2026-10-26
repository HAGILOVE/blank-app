"""Reusable cute widgets: WarpProgressBar, DropZone, PasswordEdit, ElidedLabel."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QToolButton, QWidget,
)

from . import icons, theme
from .i18n import tr


class WarpProgressBar(QWidget):
    """Progress bar where Warpy rides the leading edge and leaves sparkles behind."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._mood = "work"
        self._phase = 0.0
        self._indeterminate = False
        self.setMinimumHeight(54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def setValue(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def value(self) -> float:
        return self._value

    def setMood(self, mood: str) -> None:
        self._mood = mood
        self.update()

    def setIndeterminate(self, on: bool) -> None:
        self._indeterminate = on

    def _tick(self) -> None:
        if self._mood in ("work", "idle") or self._indeterminate:
            self._phase += 0.22
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(420, 54)

    def paintEvent(self, _e) -> None:
        pal = theme.current()
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        h = 20.0
        m = 22.0
        y = self.height() - h - 6
        track = QRectF(m, y, self.width() - 2 * m, h)
        p.setPen(QPen(QColor(pal.border), 1.5))
        p.setBrush(QColor(pal.surface2))
        p.drawRoundedRect(track, h / 2, h / 2)
        frac = 0.5 + 0.5 * math.sin(self._phase * 0.35) if self._indeterminate else self._value
        w = max(h, track.width() * frac)
        fill = QRectF(track.left(), track.top(), w, h)
        g = QLinearGradient(fill.topLeft(), fill.topRight())
        g.setColorAt(0, QColor(pal.mint))
        g.setColorAt(0.5, QColor(pal.primary))
        g.setColorAt(1, QColor(pal.pink))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(fill, h / 2, h / 2)
        # moving stripes
        path = QPainterPath()
        path.addRoundedRect(fill, h / 2, h / 2)
        p.save()
        p.setClipPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 55), 5))
        off = (self._phase * 6) % 22 if self._mood == "work" else 0
        x = fill.left() - 22 + off
        while x < fill.right() + 22:
            p.drawLine(QPointF(x, fill.bottom() + 2), QPointF(x + 14, fill.top() - 2))
            x += 22
        p.restore()
        # sparkles trail
        if self._mood == "work" and w > 60:
            for i in range(3):
                t = (self._phase * 0.5 + i * 0.9) % 3.0
                sx = fill.right() - 30 - t * 26
                if sx > fill.left() + 6:
                    a = int(255 * (1 - t / 3.0))
                    c = QColor("#FFFFFF")
                    c.setAlpha(a)
                    p.setBrush(c)
                    p.drawEllipse(QPointF(sx, track.center().y() + math.sin(self._phase + i) * 3), 2.6, 2.6)
        # mascot
        size = 44
        bob = math.sin(self._phase) * 2.5 if self._mood == "work" else 0
        pm = icons.mascot(self._mood, size)
        cx = min(max(fill.right() - 4, m + size / 2 - 6), self.width() - size / 2 - 2)
        p.drawPixmap(QPointF(cx - size / 2, y + h / 2 - size + 14 + bob), pm)
        p.end()


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", mode=Qt.ElideMiddle, parent=None) -> None:
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        super().setText(text)

    def setText(self, t: str) -> None:
        self._full = t
        self.setToolTip(t)
        self._refresh()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self) -> None:
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, self._mode, max(10, self.width())))


class PasswordEdit(QWidget):
    """Line edit with a show/hide eye button."""

    textChanged = Signal(str)

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.textChanged)
        self.btn = QToolButton()
        self.btn.setCheckable(True)
        self.btn.setIcon(icons.icon("eye"))
        self.btn.setToolTip(tr("비밀번호 보기", "Show password"))
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setAutoRaise(True)
        self.btn.toggled.connect(lambda on: self.edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.btn)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, t: str) -> None:
        self.edit.setText(t)

    def setFocus(self) -> None:  # noqa: N802
        self.edit.setFocus()

    def setEnabled(self, on: bool) -> None:  # noqa: N802
        super().setEnabled(on)


def strength(pw: str) -> tuple[int, str]:
    """Rough password strength 0..4 and a label."""
    if not pw:
        return 0, ""
    score = 0
    score += len(pw) >= 8
    score += len(pw) >= 12
    score += any(c.islower() for c in pw) and any(c.isupper() for c in pw)
    score += any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)
    labels = [tr("약함", "Weak"), tr("약함", "Weak"), tr("보통", "Fair"), tr("좋음", "Good"), tr("매우 좋음", "Strong")]
    return score, labels[score]


class StrengthBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._score = 0
        self.setFixedHeight(8)

    def set_score(self, s: int) -> None:
        self._score = s
        self.update()

    def paintEvent(self, _e) -> None:
        pal = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = 4
        gap = 4
        w = (self.width() - gap * (n - 1)) / n
        cols = ["#FF6B81", "#FFA45B", "#FFD166", "#35C98B"]
        for i in range(n):
            r = QRectF(i * (w + gap), 0, w, self.height())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cols[min(self._score, 4) - 1]) if i < self._score else QColor(pal.border))
            p.drawRoundedRect(r, 4, 4)


class DropZone(QFrame):
    """Big dashed drop target with the mascot on top."""

    filesDropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "drop")
        self.setAcceptDrops(True)

    def _set_hot(self, on: bool) -> None:
        self.setProperty("hot", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hot(True)

    def dragLeaveEvent(self, _e) -> None:
        self._set_hot(False)

    def dropEvent(self, e) -> None:
        self._set_hot(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            e.acceptProposedAction()

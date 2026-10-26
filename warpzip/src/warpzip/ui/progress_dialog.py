"""Modal progress dialog + ``run_job`` helper (runs engine work in a thread)."""
from __future__ import annotations

import time
from typing import Any, Callable, Optional, Sequence, Tuple

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ..core.fsutil import human_size, human_time
from ..core.progress import Progress
from . import icons
from .i18n import tr
from .widgets import ElidedLabel, WarpProgressBar
from .workers import JobOutcome, JobThread

Summary = Callable[[Any], Tuple[str, Sequence[Tuple[str, Callable[[], None]]]]]


class ProgressDialog(QDialog):
    def __init__(self, parent, title: str, subtitle: str, thread: JobThread,
                 summary: Optional[Summary] = None, auto_close: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.thread_ = thread
        self.summary = summary
        self.auto_close = auto_close
        self.outcome = JobOutcome()
        self._t0 = time.monotonic()
        self._title = title
        self._finished = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        head = QHBoxLayout()
        self.pic = QLabel()
        self.pic.setPixmap(icons.mascot("work", 76))
        head.addWidget(self.pic)
        col = QVBoxLayout()
        self.h = QLabel(title)
        self.h.setProperty("role", "title")
        self.sub = ElidedLabel(subtitle)
        self.sub.setProperty("role", "sub")
        col.addStretch(1)
        col.addWidget(self.h)
        col.addWidget(self.sub)
        col.addStretch(1)
        head.addLayout(col, 1)
        lay.addLayout(head)
        self.bar = WarpProgressBar()
        lay.addWidget(self.bar)
        self.current = ElidedLabel("")
        lay.addWidget(self.current)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        self.l_bytes, self.l_speed, self.l_eta, self.l_files = QLabel("-"), QLabel("-"), QLabel("-"), QLabel("-")
        for i, (k, w) in enumerate(((tr("처리량", "Processed"), self.l_bytes), (tr("속도", "Speed"), self.l_speed),
                                    (tr("남은 시간", "Remaining"), self.l_eta), (tr("파일", "Files"), self.l_files))):
            kl = QLabel(k)
            kl.setProperty("role", "hint")
            grid.addWidget(kl, 0, i)
            grid.addWidget(w, 1, i)
        lay.addLayout(grid)
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setVisible(False)
        lay.addWidget(self.result_lbl)
        self.actions = QHBoxLayout()
        self.actions.addStretch(1)
        self.pause_btn = QPushButton(tr("일시정지", "Pause"))
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.cancel_btn = QPushButton(tr("취소", "Cancel"))
        self.cancel_btn.clicked.connect(self._cancel)
        self.actions.addWidget(self.pause_btn)
        self.actions.addWidget(self.cancel_btn)
        lay.addLayout(self.actions)

        thread.progress.connect(self._on_progress)
        thread.finished.connect(self._on_finished)
        if thread.isFinished():
            QTimer.singleShot(0, self._on_finished)

    def _on_finished(self) -> None:
        if self._finished:
            return
        out = self.thread_.outcome
        if out.status == "ok":
            self._on_ok(out.result)
        elif out.status == "failed":
            self._on_fail(out.error)
        else:
            self._on_cancel()

    # -- thread callbacks ---------------------------------------------------
    def _on_progress(self, p: Progress) -> None:
        self.bar.setValue(p.fraction)
        pct = int(p.fraction * 100)
        self.setWindowTitle(f"{pct}% - {self._title}")
        if p.phase == "split":
            self.current.setText(tr("분할 중…", "Splitting…"))
        else:
            self.current.setText(p.current)
        self.l_bytes.setText(f"{human_size(p.bytes_done)} / {human_size(p.bytes_total)}" if p.bytes_total else "-")
        self.l_speed.setText(f"{human_size(p.speed)}/s" if p.speed else "-")
        self.l_eta.setText(human_time(p.eta) if p.eta >= 0 else "--:--")
        self.l_files.setText(f"{p.files_done} / {p.files_total}" if p.files_total else "-")

    def _end(self, mood: str) -> None:
        self._finished = True
        self.bar.setMood(mood)
        self.pic.setPixmap(icons.mascot(mood, 76))
        self.pause_btn.setVisible(False)
        self.cancel_btn.setVisible(False)

    def _on_ok(self, res: Any) -> None:
        self.outcome = JobOutcome("ok", res)
        self._end("happy")
        self.bar.setValue(1.0)
        self.setWindowTitle(self._title)
        if self.summary is None or self.auto_close:
            self.accept()
            return
        text, actions = self.summary(res)
        self.h.setText(tr("완료!", "All done!"))
        self.result_lbl.setText(text)
        self.result_lbl.setVisible(True)
        for label, fn in actions:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, fn=fn: (fn(), self.accept()))
            self.actions.addWidget(b)
        close = QPushButton(tr("닫기", "Close"))
        close.setProperty("class", "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        self.actions.addWidget(close)

    def _on_fail(self, ex: BaseException) -> None:
        self.outcome = JobOutcome("failed", error=ex)
        self._end("sad")
        self.accept()

    def _on_cancel(self) -> None:
        self.outcome = JobOutcome("cancelled")
        self._end("sleep")
        self.accept()

    # -- user actions ----------------------------------------------------------
    def _toggle_pause(self) -> None:
        c = self.thread_.cancel
        if c.paused:
            c.resume()
            self.pause_btn.setText(tr("일시정지", "Pause"))
            self.bar.setMood("work")
            self.pic.setPixmap(icons.mascot("work", 76))
        else:
            c.pause()
            self.pause_btn.setText(tr("계속", "Resume"))
            self.bar.setMood("sleep")
            self.pic.setPixmap(icons.mascot("sleep", 76))

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(tr("취소하는 중…", "Cancelling…"))
        self.thread_.cancel.cancel()

    def reject(self) -> None:  # Esc / window close
        if not self._finished:
            self._cancel()
        else:
            super().reject()

    def closeEvent(self, e) -> None:
        if not self._finished:
            self._cancel()
            e.ignore()
        else:
            super().closeEvent(e)


def run_job(parent, title: str, subtitle: str, fn: Callable, kind: str = "work",
            summary: Optional[Summary] = None, auto_close: bool = False, quick_ms: int = 250) -> JobOutcome:
    """Run *fn(progress_cb, cancel_token)* in a thread; show progress only if it takes a while."""
    thread = JobThread(fn)
    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    thread.start()
    QTimer.singleShot(quick_ms, loop.quit)
    loop.exec()
    if not thread.isFinished():
        dlg = ProgressDialog(parent, title, subtitle, thread, summary, auto_close)
        dlg.exec()
        thread.wait()
        return thread.outcome
    thread.wait()
    out = thread.outcome
    if out.ok and summary is not None and not auto_close:
        text, actions = summary(out.result)
        from .dialogs import message
        i = message(parent, "success", title, text,
                    buttons=[*[(l, "normal") for l, _ in actions], (tr("닫기", "Close"), "primary")])
        if 0 <= i < len(actions):
            actions[i][1]()
    return out

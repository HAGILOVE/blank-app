"""Progress reporting and cooperative cancel/pause."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .errors import Cancelled


class CancelToken:
    """Thread-safe cancel + pause switch checked by every long loop."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._run = threading.Event()
        self._run.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._run.set()  # wake a paused worker so it can exit

    def pause(self) -> None:
        self._run.clear()

    def resume(self) -> None:
        self._run.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def paused(self) -> bool:
        return not self._run.is_set()

    def check(self) -> None:
        """Raise :class:`Cancelled` if cancelled; block while paused."""
        if self._cancel.is_set():
            raise Cancelled()
        if not self._run.is_set():
            self._run.wait()
            if self._cancel.is_set():
                raise Cancelled()


@dataclass
class Progress:
    bytes_done: int = 0
    bytes_total: int = 0
    files_done: int = 0
    files_total: int = 0
    current: str = ""
    speed: float = 0.0  # bytes / second (smoothed)
    eta: float = -1.0  # seconds, -1 unknown
    phase: str = ""

    @property
    def fraction(self) -> float:
        if self.bytes_total > 0:
            return min(1.0, self.bytes_done / self.bytes_total)
        if self.files_total > 0:
            return min(1.0, self.files_done / self.files_total)
        return 0.0


ProgressCallback = Callable[[Progress], None]


class ProgressTracker:
    """Aggregates byte counts, smooths speed and throttles callbacks."""

    def __init__(
        self,
        total_bytes: int = 0,
        total_files: int = 0,
        callback: Optional[ProgressCallback] = None,
        cancel: Optional[CancelToken] = None,
        interval: float = 0.05,
    ) -> None:
        self.p = Progress(bytes_total=total_bytes, files_total=total_files)
        self.callback = callback
        self.cancel = cancel or CancelToken()
        self.interval = interval
        self._t0 = time.monotonic()
        self._last_emit = 0.0
        self._last_t = self._t0
        self._last_bytes = 0

    def set_phase(self, phase: str) -> None:
        self.p.phase = phase
        self.emit(force=True)

    def start_file(self, name: str) -> None:
        self.cancel.check()
        self.p.current = name
        self.emit()

    def end_file(self) -> None:
        self.p.files_done += 1
        self.emit()

    def add_bytes(self, n: int) -> None:
        self.cancel.check()
        self.p.bytes_done += n
        self.emit()

    def emit(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < self.interval:
            return
        dt = now - self._last_t
        if dt >= 0.25:
            inst = (self.p.bytes_done - self._last_bytes) / dt
            self.p.speed = inst if self.p.speed == 0 else 0.7 * self.p.speed + 0.3 * inst
            self._last_t = now
            self._last_bytes = self.p.bytes_done
        remaining = self.p.bytes_total - self.p.bytes_done
        self.p.eta = remaining / self.p.speed if self.p.speed > 1 and remaining >= 0 else -1.0
        self._last_emit = now
        if self.callback:
            self.callback(self.p)

    def finish(self) -> None:
        self.p.bytes_done = max(self.p.bytes_done, self.p.bytes_total)
        self.p.eta = 0.0
        self.emit(force=True)

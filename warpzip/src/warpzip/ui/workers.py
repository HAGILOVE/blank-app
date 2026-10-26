"""Run engine jobs off the GUI thread."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from PySide6.QtCore import QThread, Signal

from ..core.errors import Cancelled
from ..core.progress import CancelToken


@dataclass
class JobOutcome:
    status: str = "ok"            # ok | cancelled | failed
    result: Any = None
    error: Optional[BaseException] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class JobThread(QThread):
    progress = Signal(object)

    def __init__(self, fn: Callable[[Callable, CancelToken], Any], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self.cancel = CancelToken()
        self.outcome = JobOutcome("cancelled")

    def run(self) -> None:  # noqa: D401 - Qt override
        try:
            self.outcome = JobOutcome("ok", self._fn(self.progress.emit, self.cancel))
        except Cancelled:
            self.outcome = JobOutcome("cancelled")
        except BaseException as ex:  # noqa: BLE001 - surfaced to the UI
            self.outcome = JobOutcome("failed", error=ex)

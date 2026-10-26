"""Archive member description shared by all backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Entry:
    path: str                      # normalised, '/' separated, no trailing slash
    is_dir: bool = False
    size: int = 0                  # uncompressed bytes
    packed: int = -1               # compressed bytes, -1 = unknown
    mtime: Optional[datetime] = None
    crc: Optional[int] = None
    encrypted: bool = False
    method: str = ""
    mode: Optional[int] = None     # unix permission bits if known
    is_link: bool = False
    index: int = 0                 # archive order
    raw: Any = field(default=None, repr=False, compare=False)

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def parent(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def ratio(self) -> float:
        """Compression ratio as saved fraction (0..1); -1 when unknown."""
        if self.packed < 0 or self.size <= 0:
            return -1.0
        return max(0.0, 1.0 - self.packed / self.size)

"""Multi-volume (.001 .002 ...) support: read as one seekable file, write by splitting."""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import BinaryIO, Callable, List, Optional

from .progress import CancelToken

_VOL_RE = re.compile(r"^(?P<base>.+)\.(?P<num>\d{3})$")
CHUNK = 1024 * 1024


def volume_parts(path: Path) -> Optional[List[Path]]:
    """If *path* is part N of an 'x.ext.NNN' set return all parts in order."""
    m = _VOL_RE.match(path.name)
    if not m:
        return None
    base = m.group("base")
    parts = []
    n = 1
    while True:
        p = path.with_name(f"{base}.{n:03d}")
        if not p.exists():
            break
        parts.append(p)
        n += 1
    if len(parts) < 1 or (path.suffix != ".001" and path not in parts):
        return None
    return parts


class MultiVolumeFile(io.RawIOBase):
    """Presents several files as a single read-only seekable stream."""

    def __init__(self, parts: List[Path]) -> None:
        super().__init__()
        self._parts = list(parts)
        self._sizes = [p.stat().st_size for p in self._parts]
        self._starts = []
        acc = 0
        for s in self._sizes:
            self._starts.append(acc)
            acc += s
        self._size = acc
        self._pos = 0
        self._fh: Optional[BinaryIO] = None
        self._fh_idx = -1

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            self._pos = offset
        elif whence == os.SEEK_CUR:
            self._pos += offset
        else:
            self._pos = self._size + offset
        self._pos = max(0, self._pos)
        return self._pos

    @property
    def size(self) -> int:
        return self._size

    def _open_for(self, pos: int) -> int:
        idx = max(0, min(len(self._parts) - 1, self._bisect(pos)))
        if idx != self._fh_idx:
            if self._fh:
                self._fh.close()
            self._fh = open(self._parts[idx], "rb")
            self._fh_idx = idx
        return idx

    def _bisect(self, pos: int) -> int:
        lo, hi = 0, len(self._starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def readinto(self, b) -> int:
        if self._pos >= self._size:
            return 0
        mv = memoryview(b)
        want = len(mv)
        got = 0
        while got < want and self._pos < self._size:
            idx = self._open_for(self._pos)
            off = self._pos - self._starts[idx]
            self._fh.seek(off)
            room = self._sizes[idx] - off
            data = self._fh.read(min(room, want - got))
            if not data:
                break
            mv[got:got + len(data)] = data
            got += len(data)
            self._pos += len(data)
        return got

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
        super().close()


def split_file(
    src: Path,
    part_size: int,
    dest_base: Path,
    cancel: Optional[CancelToken] = None,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> List[Path]:
    """Split *src* into dest_base.001, .002 ... and delete *src*."""
    parts: List[Path] = []
    try:
        with open(src, "rb") as f:
            n = 1
            while True:
                data = f.read(min(CHUNK, part_size))
                if not data:
                    break
                part = dest_base.with_name(f"{dest_base.name}.{n:03d}")
                parts.append(part)
                with open(part, "wb") as out:
                    written = 0
                    while data:
                        if cancel:
                            cancel.check()
                        out.write(data)
                        written += len(data)
                        if on_bytes:
                            on_bytes(len(data))
                        if written >= part_size:
                            break
                        data = f.read(min(CHUNK, part_size - written))
                n += 1
    except BaseException:
        for p in parts:
            p.unlink(missing_ok=True)
        raise
    src.unlink(missing_ok=True)
    return parts

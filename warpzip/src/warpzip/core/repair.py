"""Rescue files from a damaged / truncated ZIP by scanning its local headers.

Typical case: an interrupted download whose central directory is missing.  Every
intact, unencrypted entry is copied into a fresh archive; entries that are
truncated, corrupt or encrypted are reported.
"""
from __future__ import annotations

import mmap
import os
import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import encoding as enc
from .compress import CompressOptions, ZipBuilder
from .progress import CancelToken, ProgressCallback, ProgressTracker

_LOCAL = struct.Struct("<4sHHHHHIIIHH")
CHUNK = 1 << 16


@dataclass
class RepairResult:
    output: Path
    recovered: int = 0
    failed: List[str] = field(default_factory=list)


@dataclass
class _Found:
    name_raw: bytes
    flags: int
    start: int
    end: int
    method: int
    mtime: float
    is_dir: bool


def _dos_time(date: int, tm: int) -> float:
    try:
        return datetime(1980 + (date >> 9), (date >> 5) & 15 or 1, date & 31 or 1,
                        tm >> 11, (tm >> 5) & 63, (tm & 31) * 2).timestamp()
    except ValueError:
        return 0.0


class _Inflate:
    """Streams the decompressed bytes of one entry out of the mmap."""

    def __init__(self, mm, f: _Found) -> None:
        self.mm, self.f = mm, f
        self.pos = f.start
        self.d = zlib.decompressobj(-15) if f.method == 8 else None
        self.crc = 0
        self.size = 0
        self.eof = False
        self.consumed_end = f.start

    def read(self, n: int = CHUNK) -> bytes:
        if self.eof:
            return b""
        if self.d is None:                       # stored
            chunk = bytes(self.mm[self.pos:min(self.pos + n, self.f.end)])
            self.pos += len(chunk)
            self.eof = not chunk or self.pos >= self.f.end
        else:
            out = b""
            while not out and not self.eof:
                raw = bytes(self.mm[self.pos:self.pos + CHUNK])
                if not raw:
                    raise EOFError("truncated")
                out = self.d.decompress(raw)
                if self.d.eof:
                    self.eof = True
                    self.consumed_end = self.pos + len(raw) - len(self.d.unused_data)
                else:
                    self.pos += len(raw)
            chunk = out
        self.crc = zlib.crc32(chunk, self.crc)
        self.size += len(chunk)
        return chunk


class _Reader:
    """File-like adapter so ZipBuilder.add_stream can pull from an _Inflate."""

    def __init__(self, inflate: _Inflate) -> None:
        self._i = inflate

    def read(self, _n: int = -1) -> bytes:
        return self._i.read()


def repair_zip(src: Path | str, dest: Path | str, progress: Optional[ProgressCallback] = None,
               cancel: Optional[CancelToken] = None) -> RepairResult:
    src, dest = Path(src), Path(dest)
    result = RepairResult(dest)
    size = src.stat().st_size
    tracker = ProgressTracker(size * 2, 0, progress, cancel)
    good: List[_Found] = []
    with open(src, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        pos = 0
        # ---- phase 1: locate + validate -----------------------------------------------------
        while True:
            tracker.cancel.check()
            i = mm.find(b"PK\x03\x04", pos)
            if i < 0 or i + _LOCAL.size > size:
                break
            (_sig, _ver, flags, method, tm, dt, crc, csize, _usize, nlen, elen) = _LOCAL.unpack(mm[i:i + _LOCAL.size])
            raw = bytes(mm[i + 30:i + 30 + nlen])
            start = i + 30 + nlen + elen
            name_txt = raw.decode("utf-8", errors="replace")
            tracker.p.bytes_done = i
            tracker.p.current = name_txt
            tracker.emit()
            pos = max(start, i + 4)
            is_dir = raw.endswith(b"/")
            if flags & 1:
                result.failed.append(f"{name_txt}: encrypted")
                continue
            if is_dir:
                good.append(_Found(raw, flags, start, start, method, _dos_time(dt, tm), True))
                continue
            found = _Found(raw, flags, start, start + csize, method, _dos_time(dt, tm), False)
            try:
                if method not in (0, 8):
                    raise ValueError("unsupported method")
                if method == 0 and flags & 8:
                    raise ValueError("unknown size")
                s = _Inflate(mm, found)
                while s.read():
                    tracker.cancel.check()
                if method == 8:
                    found.end = s.consumed_end
                if not flags & 8 and (s.crc & 0xFFFFFFFF) != crc:
                    raise ValueError("CRC mismatch")
            except (EOFError, ValueError, zlib.error) as ex:
                result.failed.append(f"{name_txt}: {ex}")
                continue
            good.append(found)
            pos = max(found.end, start)
        # ---- phase 2: write a clean archive ------------------------------------------------------
        codec = enc.detect_encoding([g.name_raw for g in good if not g.flags & 0x800])
        tmp = dest.with_name(dest.name + ".warp-part")
        zb = ZipBuilder(tmp, CompressOptions(fmt="zip", level=5))
        try:
            for g in good:
                tracker.cancel.check()
                name = g.name_raw.decode("utf-8", errors="replace") if g.flags & 0x800 else enc.decode_name(g.name_raw, codec)
                name = name.replace("\\", "/")
                if g.is_dir:
                    zb.add_dir(name.rstrip("/"), g.mtime)
                    continue
                tracker.start_file(name)
                zb.add_stream(name, g.mtime, 0o644, 0, _Reader(_Inflate(mm, g)), os.path.splitext(name)[1], tracker)
                result.recovered += 1
        except BaseException:
            zb.close()
            tmp.unlink(missing_ok=True)
            raise
        zb.close()
    os.replace(tmp, dest)
    tracker.finish()
    return result

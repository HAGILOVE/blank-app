"""File checksums with progress (MD5 / SHA-1 / SHA-256 / SHA-512 / BLAKE2 / CRC32)."""
from __future__ import annotations

import hashlib
import zlib
from pathlib import Path
from typing import Dict, Optional, Sequence

from .progress import CancelToken, ProgressCallback, ProgressTracker

ALGORITHMS = ("CRC32", "MD5", "SHA1", "SHA256", "SHA512", "BLAKE2b")


def hash_file(
    path: Path | str,
    algos: Sequence[str] = ALGORITHMS,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[CancelToken] = None,
) -> Dict[str, str]:
    path = Path(path)
    hs = {a: hashlib.new(a.lower()) for a in algos if a != "CRC32"}
    crc = 0
    tracker = ProgressTracker(path.stat().st_size, 1, progress, cancel)
    tracker.start_file(path.name)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            for h in hs.values():
                h.update(chunk)
            if "CRC32" in algos:
                crc = zlib.crc32(chunk, crc)
            tracker.add_bytes(len(chunk))
    tracker.end_file()
    tracker.finish()
    out = {a: h.hexdigest() for a, h in hs.items()}
    if "CRC32" in algos:
        out["CRC32"] = f"{crc & 0xFFFFFFFF:08x}"
    return {a: out[a] for a in algos if a in out}

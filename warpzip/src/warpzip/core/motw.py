"""Mark-of-the-Web propagation (Windows NTFS 'Zone.Identifier' stream).

Files extracted from a downloaded archive inherit the archive's zone marker so
SmartScreen / Office Protected View keep protecting the user.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

IS_WINDOWS = sys.platform == "win32"


def read_zone(archive: Path) -> Optional[bytes]:
    if not IS_WINDOWS:
        return None
    try:
        with open(f"{archive}:Zone.Identifier", "rb") as f:
            data = f.read(4096)
        return data or None
    except OSError:
        return None


def apply_zone(target: Path, zone: Optional[bytes]) -> None:
    if not IS_WINDOWS or not zone:
        return
    try:
        with open(f"{target}:Zone.Identifier", "wb") as f:
            f.write(zone)
    except OSError:
        pass  # non-NTFS volume etc.

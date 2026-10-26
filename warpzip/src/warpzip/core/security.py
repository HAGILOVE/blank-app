"""Path-safety helpers.  Every extracted name goes through here (zip-slip guard)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .errors import UnsafePath

IS_WINDOWS = sys.platform == "win32"

_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')


def sanitize_component(part: str, windows: bool = IS_WINDOWS) -> str:
    """Make one path component valid on the local file system."""
    part = part.replace("\x00", "")
    if not windows:
        return part
    part = _ILLEGAL.sub("_", part)
    part = part.rstrip(" .") or "_"
    if part.split(".")[0].upper() in _RESERVED:
        part = "_" + part
    return part


def normalize_member_name(name: str, windows: bool = IS_WINDOWS) -> str:
    """Return a safe relative '/'-separated path or raise :class:`UnsafePath`.

    * backslashes are treated as separators (zips made on Windows)
    * drive letters / UNC prefixes / leading slashes are stripped
    * any '..' component is rejected outright
    * Windows-illegal characters and reserved device names are replaced
    """
    n = name.replace("\\", "/")
    n = re.sub(r"^[A-Za-z]:", "", n)
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise UnsafePath(name)
    if not parts:
        raise UnsafePath(name)
    return "/".join(sanitize_component(p, windows) for p in parts)


def safe_join(root: Path, rel: str) -> Path:
    """Join *rel* below *root*, guaranteeing the result stays inside *root*.

    Also rejects paths that traverse an existing symlink/junction that points
    outside of *root* (symlink-based zip-slip).
    """
    root_real = Path(os.path.realpath(root))
    target = root_real.joinpath(*rel.split("/"))
    target_real = Path(os.path.realpath(target))
    try:
        target_real.relative_to(root_real)
    except ValueError:
        raise UnsafePath(rel) from None
    return root.joinpath(*rel.split("/"))


def unique_path(path: Path) -> Path:
    """Return *path* or 'name (1).ext', 'name (2).ext' ... if it exists."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    if path.name.lower().endswith(".tar.gz"):
        stem, suffix = path.name[:-7], ".tar.gz"
    i = 1
    while True:
        cand = path.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1


def long_path(p: Path) -> Path:
    r"""Prefix with \\?\ on Windows when the path nears MAX_PATH (260)."""
    if not IS_WINDOWS:
        return p
    s = os.path.abspath(str(p))
    if len(s) < 240 or s.startswith("\\\\?\\"):
        return p
    if s.startswith("\\\\"):                 # UNC share
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)

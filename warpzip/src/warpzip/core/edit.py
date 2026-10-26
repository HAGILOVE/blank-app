"""Modify an existing ZIP: add files, delete entries, rename (rewrite + swap)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from .archive import open_archive
from .compress import CompressOptions, ZipBuilder, collect_sources
from .errors import UnsupportedFormat
from .progress import CancelToken, ProgressCallback, ProgressTracker


def edit_zip(
    path: Path | str,
    remove: Iterable[str] = (),
    add: Sequence[Path | str] = (),
    add_prefix: str = "",
    rename: Optional[Dict[str, str]] = None,
    password: Optional[str] = None,
    opts: Optional[CompressOptions] = None,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[CancelToken] = None,
) -> None:
    """Rewrite *path* without the entries in *remove*, with *add* appended.

    * ``remove`` entries match by exact path or as a folder prefix.
    * ``rename`` maps old path -> new path (folders rename their children).
    * Every name is written back as UTF-8, which also repairs legacy code-page names.
    * Existing encryption is preserved when ``password`` is given.
    """
    path = Path(path)
    rename = rename or {}
    o = opts or CompressOptions(fmt="zip")
    o.fmt = "zip"
    o.password = password if password is not None else o.password
    remove_set = {r.strip("/") for r in remove}

    def removed(name: str) -> bool:
        return any(name == r or name.startswith(r + "/") for r in remove_set)

    def renamed(name: str) -> str:
        for old, new in rename.items():
            if name == old:
                return new
            if name.startswith(old + "/"):
                return new + name[len(old):]
        return name

    skipped: list = []
    items = collect_sources(add, o.exclude, skip=[path], skipped=skipped)
    if add_prefix:
        for it in items:
            it.arcname = f"{add_prefix.strip('/')}/{it.arcname}"
    new_names = {i.arcname for i in items}

    reader = open_archive(path, password=o.password)
    if reader.fmt != "zip":
        reader.close()
        raise UnsupportedFormat(reader.fmt)
    keep = [e for e in reader.entries if not removed(e.path) and renamed(e.path) not in new_names]
    total = sum(e.size for e in keep if not e.is_dir) + sum(i.size for i in items)
    tracker = ProgressTracker(total, len(keep) + len(items), progress, cancel)
    tmp = path.with_name(path.name + ".warp-part")
    try:
        zb = ZipBuilder(tmp, o)
        try:
            for e in keep:
                tracker.start_file(e.path)
                name = renamed(e.path)
                ts = e.mtime.timestamp() if e.mtime else 0.0
                if e.is_dir:
                    zb.add_dir(name, ts, (e.mode or 0o755) & 0o777)
                else:
                    store = e.raw.compress_type == 0
                    with reader.open_member(e) as src:
                        zb.add_stream(name, ts, (e.mode or 0o644) & 0o777, e.size, src,
                                      Path(name).suffix, tracker, store=store)
                tracker.end_file()
            for it in items:
                tracker.start_file(it.arcname)
                if it.is_dir:
                    zb.add_dir(it.arcname, it.mtime)
                else:
                    with open(it.path, "rb") as src:
                        zb.add_stream(it.arcname, it.mtime, 0o644, it.size, src, it.path.suffix, tracker)
                tracker.end_file()
        finally:
            zb.close()
            reader.close()
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tracker.finish()

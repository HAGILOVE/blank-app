"""Destination side of an extraction: path safety, conflict policy, writing."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, List, Optional

from . import motw
from .entry import Entry
from .errors import UnsafePath
from .progress import CancelToken, ProgressTracker
from .security import IS_WINDOWS, long_path, normalize_member_name, safe_join, unique_path

CHUNK = 1024 * 1024

OVERWRITE = "overwrite"
SKIP = "skip"
RENAME = "rename"
NEWER = "newer"


@dataclass
class ExtractOptions:
    folder_mode: str = "smart"        # smart | always | never
    overwrite: str = OVERWRITE        # overwrite | skip | rename | newer
    encoding: Optional[str] = None    # None/auto -> detect
    propagate_motw: bool = True
    extract_links: bool = False
    restore_mtime: bool = True
    strip_prefix: str = ""            # drop this leading folder (extract from sub-folder view)


@dataclass
class ExtractResult:
    root: Path
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    skipped: List[str] = field(default_factory=list)
    unsafe: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def strip_prefix(path: str, prefix: str) -> str:
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix) + 1:]
    return path


class Sink:
    def __init__(
        self,
        root: Path,
        opts: ExtractOptions,
        tracker: ProgressTracker,
        result: ExtractResult,
        zone: Optional[bytes] = None,
    ) -> None:
        self.root = root
        self.opts = opts
        self.tracker = tracker
        self.cancel: CancelToken = tracker.cancel
        self.result = result
        self.zone = zone if opts.propagate_motw else None
        self._dir_stamps: List[tuple[Path, Entry]] = []
        root.mkdir(parents=True, exist_ok=True)

    # -- path resolution -------------------------------------------------
    def resolve(self, entry: Entry) -> Optional[Path]:
        """Return the final path for *entry* or None when it must be skipped."""
        if entry.is_link and not self.opts.extract_links:
            self.result.skipped.append(entry.path)
            return None
        try:
            rel = normalize_member_name(strip_prefix(entry.path, self.opts.strip_prefix))
            target = safe_join(self.root, rel)
        except UnsafePath:
            self.result.unsafe.append(entry.path)
            return None
        target = long_path(target)
        if entry.is_dir:
            return target
        if target.exists() or target.is_symlink():
            if target.is_dir():
                self.result.skipped.append(entry.path)
                return None
            pol = self.opts.overwrite
            if pol == SKIP:
                self.result.skipped.append(entry.path)
                return None
            if pol == NEWER and entry.mtime is not None:
                try:
                    if target.stat().st_mtime >= entry.mtime.timestamp():
                        self.result.skipped.append(entry.path)
                        return None
                except OSError:
                    pass
            if pol == RENAME:
                target = unique_path(target)
            else:
                self._make_writable(target)
        return target

    @staticmethod
    def _make_writable(p: Path) -> None:
        try:
            os.chmod(p, os.stat(p).st_mode | stat.S_IWRITE)
        except OSError:
            pass

    # -- writing ----------------------------------------------------------
    def make_dir(self, entry: Entry) -> None:
        target = self.resolve(entry)
        if target is None:
            return
        target.mkdir(parents=True, exist_ok=True)
        self.result.dirs += 1
        self._dir_stamps.append((target, entry))

    def finalize(self) -> None:
        """Re-apply directory timestamps (writing files touched them)."""
        for target, entry in reversed(self._dir_stamps):
            self._stamp(target, entry)
        self._dir_stamps.clear()

    def adopt(self, entry: Entry, tmp_file: Path) -> bool:
        """Move an already-extracted temp file into place (external engine)."""
        import shutil

        self.tracker.start_file(entry.path)
        target = self.resolve(entry)
        if target is None:
            self.tracker.end_file()
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self._make_writable(target)
        shutil.move(str(tmp_file), str(target))
        self.result.bytes += entry.size
        self.finish_file(target, entry)
        self.tracker.end_file()
        return True

    def open_target(self, entry: Entry) -> Optional[tuple[Path, BinaryIO]]:
        target = self.resolve(entry)
        if target is None:
            return None
        parent = target.parent
        if parent.exists() and not parent.is_dir():
            self.result.errors.append(f"{entry.path}: parent is a file")
            return None
        parent.mkdir(parents=True, exist_ok=True)
        return target, open(target, "wb")

    def write_stream(self, entry: Entry, src: BinaryIO) -> bool:
        """Copy *src* to the destination for *entry*. Returns True when written."""
        self.tracker.start_file(entry.path)
        opened = self.open_target(entry)
        if opened is None:
            if entry.size:
                self.tracker.p.bytes_done += entry.size  # keep the bar honest
            self.tracker.end_file()
            return False
        target, out = opened
        ok = False
        try:
            with out:
                while True:
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    self.result.bytes += len(chunk)
                    self.tracker.add_bytes(len(chunk))
            ok = True
        finally:
            if not ok:
                try:
                    target.unlink()
                except OSError:
                    pass
        self.finish_file(target, entry)
        self.tracker.end_file()
        return True

    def finish_file(self, target: Path, entry: Entry) -> None:
        self.result.files += 1
        self._stamp(target, entry)
        if not IS_WINDOWS and entry.mode:
            try:
                os.chmod(target, (entry.mode & 0o777) & ~0o6000 | 0o600)
            except OSError:
                pass
        motw.apply_zone(target, self.zone)

    def _stamp(self, target: Path, entry: Entry) -> None:
        if self.opts.restore_mtime and entry.mtime is not None:
            try:
                ts = entry.mtime.timestamp()
                os.utime(target, (ts, ts))
            except (OSError, OverflowError, ValueError):
                pass

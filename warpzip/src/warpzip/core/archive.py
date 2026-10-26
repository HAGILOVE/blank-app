"""Open archives and run extract / test jobs."""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from . import motw
from .entry import Entry
from .errors import (
    DiskSpaceError, UnsupportedFormat,
)
from .formats import FORMATS, archive_stem, sniff
from .progress import CancelToken, ProgressCallback, ProgressTracker
from .readers import (
    ArchiveReader, ExternalReader, SevenZipReader, SingleReader, TarReader, ZipReader,
)
from .sink import ExtractOptions, ExtractResult, Sink, strip_prefix
from .volumes import MultiVolumeFile, volume_parts


def open_archive(
    path: Path | str,
    password: Optional[str] = None,
    encoding: Optional[str] = None,
) -> ArchiveReader:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    parts = volume_parts(path)
    source = MultiVolumeFile(parts) if parts else path
    try:
        if parts:
            fmt = sniff(source, path.name[:-4])
        else:
            with open(path, "rb") as f:
                fmt = sniff(f, path.name)
    except OSError:
        fmt = None
    if fmt is None:
        raise UnsupportedFormat(path.name)
    try:
        if fmt == "zip":
            return ZipReader(path, source, password, encoding)
        if fmt == "7z":
            return SevenZipReader(path, source, password, encoding)
        if fmt.startswith("tar"):
            comp = fmt.split(".", 1)[1] if "." in fmt else ""
            return TarReader(path, source, password, encoding, comp)
        if fmt in ("gz", "bz2", "xz", "zst"):
            return SingleReader(path, source, password, encoding, fmt)
        info = FORMATS.get(fmt)
        if info is not None and not info.native:
            return ExternalReader(path, source, password, encoding, fmt)
    except BaseException:
        if isinstance(source, MultiVolumeFile):
            source.close()
        raise
    raise UnsupportedFormat(fmt)


@dataclass
class ArchiveStats:
    files: int = 0
    dirs: int = 0
    total_size: int = 0
    packed_size: int = 0
    encrypted: bool = False
    top_level: List[str] = field(default_factory=list)
    suspicious: bool = False
    reason: str = ""

    @property
    def ratio(self) -> float:
        if self.total_size <= 0:
            return 0.0
        return max(0.0, 1.0 - self.packed_size / self.total_size)


#: ratio above which an archive is treated as a possible decompression bomb
BOMB_RATIO = 200
BOMB_MIN_BYTES = 2 * 1024 ** 3


def analyze(reader: ArchiveReader) -> ArchiveStats:
    st = ArchiveStats(encrypted=reader.encrypted, packed_size=reader.packed_size)
    tops: dict = {}
    for e in reader.entries:
        if e.is_dir:
            st.dirs += 1
        else:
            st.files += 1
            st.total_size += e.size
        tops.setdefault(e.path.split("/", 1)[0], True)
    st.top_level = list(tops)
    if st.packed_size > 0 and st.total_size >= BOMB_MIN_BYTES and st.total_size / st.packed_size >= BOMB_RATIO:
        st.suspicious = True
        st.reason = "ratio"
    if st.files > 500_000:
        st.suspicious = True
        st.reason = "count"
    return st


def _check_space(dest: Path, need: int) -> None:
    probe = dest
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if need > free:
        raise DiskSpaceError(f"{need}:{free}")


def target_root(reader: ArchiveReader, dest: Path, opts: ExtractOptions, entries: Sequence[Entry]) -> Path:
    mode = opts.folder_mode
    if mode == "never":
        return dest
    stem = archive_stem(reader.path.name) or "extracted"
    if mode == "always":
        return dest / stem
    tops = {strip_prefix(e.path, opts.strip_prefix).split("/", 1)[0]
            for e in entries if strip_prefix(e.path, opts.strip_prefix) != opts.strip_prefix}
    return dest if len(tops) <= 1 else dest / stem


def extract(
    reader: ArchiveReader,
    dest: Path | str,
    entries: Optional[Sequence[Entry]] = None,
    opts: Optional[ExtractOptions] = None,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[CancelToken] = None,
) -> ExtractResult:
    opts = opts or ExtractOptions()
    dest = Path(dest)
    entries = list(entries) if entries is not None else list(reader.entries)
    root = target_root(reader, dest, opts, entries)
    total = reader.estimated_total(entries)
    _check_space(dest, total)
    tracker = ProgressTracker(total, sum(1 for e in entries if not e.is_dir), progress, cancel)
    result = ExtractResult(root=root)
    zone = motw.read_zone(reader.path) if opts.propagate_motw else None
    sink = Sink(root, opts, tracker, result, zone)
    try:
        reader.extract(entries, sink)
    finally:
        sink.finalize()
    tracker.finish()
    return result


def verify_archive(
    reader: ArchiveReader,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[CancelToken] = None,
) -> List[str]:
    total = reader.estimated_total(reader.entries)
    tracker = ProgressTracker(total, sum(1 for e in reader.entries if not e.is_dir), progress, cancel)
    problems = reader.test(tracker)
    tracker.finish()
    return problems

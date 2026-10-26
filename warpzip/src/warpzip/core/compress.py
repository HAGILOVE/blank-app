"""Write-side: build archives from files and folders."""
from __future__ import annotations

import fnmatch
import io
import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, List, Optional, Sequence

import pyzipper

from .errors import UnsupportedFormat, WarpError
from .formats import FORMATS
from .fsutil import move_to_recycle_bin
from .progress import CancelToken, ProgressCallback, ProgressTracker
from .volumes import split_file

try:
    import py7zr
except ImportError:  # pragma: no cover
    py7zr = None
try:
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None

CHUNK = 1024 * 1024

DEFAULT_EXCLUDES = ["Thumbs.db", "desktop.ini", ".DS_Store", "__MACOSX", "~$*"]

#: already-compressed formats are STOREd in "smart store" mode (huge speed-up)
INCOMPRESSIBLE = {
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".zst", ".lz4", ".cab", ".jar", ".apk",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".avif", ".jxl",
    ".mp3", ".aac", ".m4a", ".ogg", ".opus", ".flac", ".wma",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".m4v", ".flv",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub", ".pdf",
    ".woff", ".woff2",
}

#: UI level (0 store, 1 warp, 3 fast, 5 normal, 7 max, 9 ultra) -> per-codec level
_ZSTD = {1: 1, 2: 2, 3: 3, 4: 6, 5: 9, 6: 12, 7: 15, 8: 17, 9: 19}


@dataclass
class CompressOptions:
    fmt: str = "zip"
    level: int = 5
    zip_method: str = "deflate"      # deflate | bzip2 | lzma
    password: Optional[str] = None
    encrypt_names: bool = False      # 7z only
    split_size: int = 0              # bytes, 0 = single file
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    smart_store: bool = True
    delete_sources: bool = False
    comment: str = ""
    follow_symlinks: bool = False


@dataclass
class SourceItem:
    path: Path
    arcname: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0


@dataclass
class CompressResult:
    outputs: List[Path]
    files: int = 0
    dirs: int = 0
    original: int = 0
    packed: int = 0
    skipped: List[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return max(0.0, 1.0 - self.packed / self.original) if self.original else 0.0


def _excluded(name: str, rel: str, patterns: Sequence[str]) -> bool:
    low_name, low_rel = name.lower(), rel.lower()
    for pat in patterns:
        p = pat.lower().strip()
        if not p:
            continue
        if fnmatch.fnmatch(low_name, p) or fnmatch.fnmatch(low_rel, p):
            return True
    return False


def collect_sources(
    paths: Iterable[Path | str],
    exclude: Sequence[str] = (),
    skip: Iterable[Path] = (),
    follow_symlinks: bool = False,
    skipped: Optional[List[str]] = None,
) -> List[SourceItem]:
    """Expand files/folders into a flat, ordered list of archive members."""
    skip_set = {os.path.normcase(os.path.abspath(p)) for p in skip}
    items: List[SourceItem] = []
    seen: set = set()

    def add(p: Path, arc: str, is_dir: bool) -> None:
        key = arc
        if key in seen:
            return
        seen.add(key)
        try:
            st = p.stat()
        except OSError:
            if skipped is not None:
                skipped.append(str(p))
            return
        items.append(SourceItem(p, arc, is_dir, 0 if is_dir else st.st_size, st.st_mtime))

    def walk(p: Path, arc: str) -> None:
        if os.path.normcase(os.path.abspath(p)) in skip_set:
            return
        if _excluded(p.name, arc, exclude):
            return
        if p.is_symlink() and not follow_symlinks:
            if skipped is not None:
                skipped.append(str(p))
            return
        if p.is_dir():
            add(p, arc, True)
            try:
                children = sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
            except OSError:
                if skipped is not None:
                    skipped.append(str(p))
                return
            for c in children:
                walk(c, f"{arc}/{c.name}")
        elif p.is_file():
            add(p, arc, False)

    for raw in paths:
        p = Path(raw)
        walk(p, p.name or str(p).rstrip("\\/").replace(":", ""))
    return items


class _ProgressReader(io.BufferedReader):
    """File wrapper reporting consumed bytes and honouring cancel."""

    def __init__(self, path: Path, tracker: ProgressTracker):
        super().__init__(io.FileIO(path, "rb"), buffer_size=CHUNK)
        self._tracker = tracker

    def read(self, size=-1):
        data = super().read(size)
        if data:
            self._tracker.add_bytes(len(data))
        return data

    def read1(self, size=-1):
        data = super().read1(size)
        if data:
            self._tracker.add_bytes(len(data))
        return data


class _CountingWriter(io.RawIOBase):
    """Wraps an output file to feed a compressor stream (zstd)."""

    def __init__(self, fh: BinaryIO):
        self.fh = fh

    def writable(self):
        return True

    def write(self, b):
        return self.fh.write(b)


def _dt(ts: float) -> tuple:
    d = datetime.fromtimestamp(ts) if ts else datetime(1980, 1, 1)
    if d.year < 1980:
        return (1980, 1, 1, 0, 0, 0)
    if d.year > 2107:
        return (2107, 12, 31, 23, 59, 58)
    return (d.year, d.month, d.day, d.hour, d.minute, d.second)


# --------------------------------------------------------------------- zip
class ZipBuilder:
    """Thin wrapper around pyzipper that writes AES-256 / plain ZIPs."""

    def __init__(self, out: Path, o: CompressOptions):
        self.o = o
        method = {"deflate": zipfile.ZIP_DEFLATED, "bzip2": zipfile.ZIP_BZIP2,
                  "lzma": zipfile.ZIP_LZMA}.get(o.zip_method, zipfile.ZIP_DEFLATED)
        self.base = zipfile.ZIP_STORED if o.level == 0 else method
        self.lvl = max(1, min(9, o.level)) if self.base in (zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2) else None
        self.zf = pyzipper.AESZipFile(str(out), "w", compression=self.base, allowZip64=True)
        if o.password:
            self.zf.setpassword(o.password.encode("utf-8"))
            self.zf.setencryption(pyzipper.WZ_AES, nbits=256)
        if o.comment:
            self.zf.comment = o.comment.encode("utf-8")

    def add_dir(self, arcname: str, mtime: float, mode: int = 0o755) -> None:
        zi = self.zf.zipinfo_cls(arcname.rstrip("/") + "/", date_time=_dt(mtime))
        zi.external_attr = ((stat.S_IFDIR | mode) << 16) | 0x10
        zi.compress_type = zipfile.ZIP_STORED
        zf = self.zf
        saved = (zf.pwd, zf.encryption, zf.encryption_kwargs)
        zf.pwd, zf.encryption, zf.encryption_kwargs = None, None, None  # dirs carry no data
        try:
            zf.writestr(zi, b"")
        finally:
            zf.pwd, zf.encryption, zf.encryption_kwargs = saved

    def add_stream(self, arcname: str, mtime: float, mode: int, size: int, src: BinaryIO,
                   suffix: str, tracker: ProgressTracker, store: bool = False) -> None:
        zi = self.zf.zipinfo_cls(arcname, date_time=_dt(mtime))
        zi.external_attr = (stat.S_IFREG | mode) << 16
        ctype = self.base
        if ctype != zipfile.ZIP_STORED and (store or (self.o.smart_store and suffix.lower() in INCOMPRESSIBLE)):
            ctype = zipfile.ZIP_STORED
        zi.compress_type = ctype
        zi._compresslevel = self.lvl if ctype in (zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2) else None
        with self.zf.open(zi, "w", force_zip64=size > (1 << 30)) as dst:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                dst.write(chunk)
                tracker.add_bytes(len(chunk))

    def close(self) -> None:
        self.zf.close()


def _write_zip(items: List[SourceItem], out: Path, o: CompressOptions, tracker: ProgressTracker) -> None:
    zb = ZipBuilder(out, o)
    try:
        for it in items:
            tracker.start_file(it.arcname)
            try:
                mode = stat.S_IMODE(it.path.stat().st_mode)
            except OSError:
                mode = 0o755 if it.is_dir else 0o644
            if it.is_dir:
                zb.add_dir(it.arcname, it.mtime, mode)
            else:
                with open(it.path, "rb") as src:
                    zb.add_stream(it.arcname, it.mtime, mode, it.size, src, it.path.suffix, tracker)
            tracker.end_file()
    finally:
        zb.close()


# ---------------------------------------------------------------------- 7z
def _write_7z(items: List[SourceItem], out: Path, o: CompressOptions, tracker: ProgressTracker) -> None:
    if py7zr is None:  # pragma: no cover
        raise UnsupportedFormat("py7zr missing")
    if o.level == 0:
        filters = [{"id": py7zr.FILTER_COPY}]
    else:
        filters = [{"id": py7zr.FILTER_LZMA2, "preset": min(9, o.level)}]
    if o.password:
        # py7zr only encrypts when the AES filter is part of an explicit filter chain
        filters.append({"id": py7zr.FILTER_CRYPTO_AES256_SHA256})
    with py7zr.SevenZipFile(str(out), "w", filters=filters, password=o.password or None,
                            header_encryption=bool(o.password and o.encrypt_names)) as sz:
        for it in items:
            tracker.start_file(it.arcname)
            if it.is_dir or it.size == 0:
                sz.write(it.path, it.arcname)
                tracker.end_file()
                continue
            with _ProgressReader(it.path, tracker) as src:
                sz.writef(src, it.arcname)
            _patch_7z_time(sz, it)
            tracker.end_file()


def _patch_7z_time(sz, it: SourceItem) -> None:
    """writef() stamps 'now'; restore the real modification time."""
    try:
        from py7zr.helpers import ArchiveTimestamp

        info = sz.header.files_info.files[-1]
        ts = ArchiveTimestamp.from_datetime(datetime.fromtimestamp(it.mtime).astimezone())
        info["lastwritetime"] = ts
        info["creationtime"] = ts
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- tar
def _write_tar(items: List[SourceItem], out: Path, o: CompressOptions, tracker: ProgressTracker) -> None:
    fmt = o.fmt
    lvl = max(1, min(9, o.level))
    cleanup: List[Callable[[], None]] = []
    if fmt == "tar":
        tf = tarfile.open(out, "w", format=tarfile.PAX_FORMAT)
    elif fmt == "tar.gz":
        tf = tarfile.open(out, "w:gz", compresslevel=lvl if o.level else 1, format=tarfile.PAX_FORMAT)
    elif fmt == "tar.bz2":
        tf = tarfile.open(out, "w:bz2", compresslevel=lvl, format=tarfile.PAX_FORMAT)
    elif fmt == "tar.xz":
        tf = tarfile.open(out, "w:xz", preset=min(9, o.level), format=tarfile.PAX_FORMAT)
    elif fmt == "tar.zst":
        if zstandard is None:  # pragma: no cover
            raise UnsupportedFormat("zstandard missing")
        fh = open(out, "wb")
        cctx = zstandard.ZstdCompressor(level=_ZSTD.get(max(1, o.level), 9), threads=-1)
        zw = cctx.stream_writer(fh, closefd=False)
        tf = tarfile.open(fileobj=zw, mode="w|", format=tarfile.PAX_FORMAT)
        cleanup += [zw.close, fh.close]
    else:  # pragma: no cover
        raise UnsupportedFormat(fmt)
    try:
        for it in items:
            tracker.start_file(it.arcname)
            ti = tf.gettarinfo(str(it.path), it.arcname)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            if ti.isreg():
                with _ProgressReader(it.path, tracker) as src:
                    tf.addfile(ti, src)
            else:
                tf.addfile(ti)
            tracker.end_file()
    finally:
        tf.close()
        for c in cleanup:
            c()


_WRITERS = {"zip": _write_zip, "7z": _write_7z}


def compress(
    sources: Sequence[Path | str],
    dest: Path | str,
    opts: Optional[CompressOptions] = None,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[CancelToken] = None,
) -> CompressResult:
    """Create *dest* from *sources*. Writes atomically (temp file + rename)."""
    o = opts or CompressOptions()
    info = FORMATS.get(o.fmt)
    if info is None or not info.can_write:
        raise UnsupportedFormat(o.fmt)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".warp-part")
    skipped: List[str] = []
    items = collect_sources(sources, o.exclude, skip=[dest, tmp], follow_symlinks=o.follow_symlinks,
                            skipped=skipped)
    if not items:
        raise WarpError("nothing to compress")
    total = sum(i.size for i in items)
    if o.split_size:
        total_progress = total * 2   # compress pass + split pass
    else:
        total_progress = total
    tracker = ProgressTracker(total_progress, sum(1 for i in items if not i.is_dir), progress, cancel)
    writer = _WRITERS.get(o.fmt, _write_tar)
    try:
        writer(items, tmp, o, tracker)
        packed = tmp.stat().st_size
        outputs: List[Path]
        if o.split_size and packed > o.split_size:
            tracker.p.bytes_done = total
            tracker.set_phase("split")
            outputs = split_file(tmp, o.split_size, dest, tracker.cancel, None)
        else:
            os.replace(tmp, dest)
            outputs = [dest]
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tracker.finish()
    res = CompressResult(
        outputs=outputs, files=sum(1 for i in items if not i.is_dir),
        dirs=sum(1 for i in items if i.is_dir), original=total,
        packed=sum(p.stat().st_size for p in outputs), skipped=skipped,
    )
    if o.delete_sources:
        roots = [Path(s) for s in sources]
        if not move_to_recycle_bin(roots):
            pass  # never hard-delete user data when the recycle bin is unavailable
    return res

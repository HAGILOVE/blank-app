"""Read-side backends.  One class per container family."""
from __future__ import annotations

import bz2
import gzip
import io
import lzma
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence

import pyzipper

from . import encoding as enc
from .entry import Entry
from .errors import (
    Cancelled, CorruptArchive, PasswordRequired, ToolMissing, UnsupportedFormat, WrongPassword,
)
from .progress import ProgressTracker
from .sink import Sink
from .volumes import MultiVolumeFile

try:
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None
_ZSTD_ERROR = zstandard.ZstdError if zstandard else OSError

try:
    import py7zr
    from py7zr.io import Py7zIO, WriterFactory
except ImportError:  # pragma: no cover
    py7zr = None


class ArchiveReader:
    """Common interface.  Subclasses fill ``entries`` in ``__init__``."""

    fmt = ""

    def __init__(self, path: Path, source, password: Optional[str], encoding: Optional[str]):
        self.path = path
        self.source = source          # Path or file-like (multi-volume)
        self.password = password
        self.encoding = None if encoding in (None, "", "auto") else encoding
        self.entries: List[Entry] = []
        self.encrypted = False
        self.comment = ""
        self.detected_encoding: Optional[str] = None
        self.packed_size = path.stat().st_size if path.exists() else 0
        if isinstance(source, MultiVolumeFile):
            self.packed_size = source.size

    # -- API --------------------------------------------------------------
    def open_member(self, entry: Entry) -> BinaryIO:  # pragma: no cover - abstract
        raise NotImplementedError

    def estimated_total(self, entries: Sequence[Entry]) -> int:
        return sum(e.size for e in entries if not e.is_dir)

    def extract(self, entries: Sequence[Entry], sink: Sink) -> None:
        for e in sorted(entries, key=lambda x: x.index):
            sink.cancel.check()
            if e.is_dir:
                sink.make_dir(e)
                continue
            with self.open_member(e) as src:
                sink.write_stream(e, src)

    def test(self, tracker: ProgressTracker) -> List[str]:
        """Read every member and verify checksums. Returns problem descriptions."""
        problems: List[str] = []
        for e in self.entries:
            if e.is_dir:
                continue
            tracker.start_file(e.path)
            try:
                with self.open_member(e) as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        tracker.add_bytes(len(chunk))
            except Cancelled:
                raise
            except (PasswordRequired, WrongPassword):
                raise
            except Exception as ex:  # noqa: BLE001
                problems.append(f"{e.path}: {ex}")
            tracker.end_file()
        return problems

    def verify_password(self) -> None:
        """Raise WrongPassword/PasswordRequired when the password is bad."""
        for e in self.entries:
            if e.encrypted and not e.is_dir and e.size > 0:
                with self.open_member(e) as src:
                    src.read(16)
                return

    def set_password(self, password: Optional[str]) -> None:
        self.password = password

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------- ZIP
class ZipReader(ArchiveReader):
    fmt = "zip"

    def __init__(self, path, source, password, encoding):
        super().__init__(path, source, password, encoding)
        try:
            self.zf = pyzipper.AESZipFile(source if not isinstance(source, Path) else str(source))
        except (zipfile.BadZipFile, pyzipper.zipfile.BadZipFile) as ex:
            raise CorruptArchive(str(ex)) from ex
        if password:
            self.zf.setpassword(password.encode("utf-8"))
        self.comment = self.zf.comment.decode("utf-8", errors="replace") if self.zf.comment else ""
        infos = self.zf.infolist()
        raws = [enc.zip_raw_name(i.orig_filename, i.flag_bits) for i in infos]
        codec = self.encoding
        if codec is None:
            codec = enc.detect_encoding(r for r in raws if r)
            self.detected_encoding = codec
        for idx, (info, raw) in enumerate(zip(infos, raws, strict=True)):
            name = info.orig_filename
            if raw is not None:
                uni = enc.parse_unicode_path_extra(info.extra, raw)
                name = uni if uni is not None else enc.decode_name(raw, codec)
            name = name.replace("\\", "/")
            is_dir = name.endswith("/")
            name = name.strip("/")
            if not name:
                continue
            attr = info.external_attr >> 16
            is_link = info.create_system == 3 and stat.S_ISLNK(attr)
            try:
                mtime = datetime(*info.date_time)
            except ValueError:
                mtime = None
            enc_flag = bool(info.flag_bits & 0x1)
            self.encrypted = self.encrypted or enc_flag
            method = {0: "Store", 8: "Deflate", 12: "BZip2", 14: "LZMA", 93: "Zstd", 99: "AES"}.get(
                info.compress_type, str(info.compress_type))
            self.entries.append(Entry(
                path=name, is_dir=is_dir or info.is_dir(), size=info.file_size,
                packed=info.compress_size, mtime=mtime, crc=info.CRC, encrypted=enc_flag,
                method=method, mode=(attr & 0o7777) if info.create_system == 3 and attr else None,
                is_link=is_link, index=idx, raw=info,
            ))

    def open_member(self, entry: Entry) -> BinaryIO:
        try:
            return self.zf.open(entry.raw)
        except RuntimeError as ex:
            self._map_runtime(ex)
        except zipfile.BadZipFile as ex:
            raise CorruptArchive(str(ex)) from ex
        except NotImplementedError as ex:
            raise UnsupportedFormat(str(ex)) from ex

    def set_password(self, password):
        self.password = password
        self.zf.setpassword(password.encode("utf-8") if password else None)

    def _map_runtime(self, ex: RuntimeError):
        msg = str(ex).lower()
        if "password required" in msg or "encrypted" in msg and not self.password:
            raise PasswordRequired(str(ex)) from ex
        if "password" in msg:
            raise WrongPassword(str(ex)) from ex
        raise ex

    def extract(self, entries, sink):
        try:
            super().extract(entries, sink)
        except RuntimeError as ex:
            self._map_runtime(ex)
        except zipfile.BadZipFile as ex:
            raise CorruptArchive(str(ex)) from ex

    def close(self):
        self.zf.close()


# ---------------------------------------------------------------------- TAR
class TarReader(ArchiveReader):
    fmt = "tar"

    def __init__(self, path, source, password, encoding, compression: str = ""):
        super().__init__(path, source, password, encoding)
        self.compression = compression
        self._enc = self.encoding or "utf-8"
        try:
            with self._open() as tf:
                for idx, ti in enumerate(tf):
                    name = ti.name
                    while name.startswith("./"):
                        name = name[2:]
                    name = name.strip("/")
                    if not name or name == ".":
                        continue
                    special = not (ti.isreg() or ti.isdir())
                    self.entries.append(Entry(
                        path=name, is_dir=ti.isdir(), size=ti.size if ti.isreg() else 0,
                        mtime=datetime.fromtimestamp(ti.mtime) if ti.mtime else None,
                        mode=ti.mode, is_link=special, method=compression or "tar", index=idx,
                    ))
        except tarfile.TarError as ex:
            raise CorruptArchive(str(ex)) from ex
        except (OSError, EOFError, lzma.LZMAError, _ZSTD_ERROR) as ex:
            raise CorruptArchive(str(ex)) from ex

    def _raw(self):
        if isinstance(self.source, Path):
            return open(self.source, "rb")
        self.source.seek(0)
        return self.source

    def _open(self) -> tarfile.TarFile:
        raw = self._raw()
        if self.compression == "zst":
            if zstandard is None:  # pragma: no cover
                raise UnsupportedFormat("zstandard module missing")
            raw = zstandard.ZstdDecompressor().stream_reader(raw)
        return tarfile.open(fileobj=raw, mode="r|" if self.compression == "zst" else "r|*",
                            encoding=self._enc, errors="replace")

    def _iter(self, wanted: dict):
        with self._open() as tf:
            for idx, ti in enumerate(tf):
                if idx in wanted:
                    yield wanted[idx], tf, ti

    def open_member(self, entry: Entry) -> BinaryIO:
        for _e, tf, ti in self._iter({entry.index: entry}):
            data = tf.extractfile(ti)
            buf = io.BytesIO(data.read() if data else b"")
            return buf
        raise CorruptArchive(entry.path)

    def extract(self, entries, sink):
        wanted = {e.index: e for e in entries}
        remaining = len(wanted)
        try:
            for e, tf, ti in self._iter(wanted):
                sink.cancel.check()
                if e.is_dir:
                    sink.make_dir(e)
                elif e.is_link:
                    sink.result.skipped.append(e.path)
                else:
                    src = tf.extractfile(ti)
                    if src is None:
                        continue
                    sink.write_stream(e, src)
                remaining -= 1
                if remaining <= 0:
                    break
        except tarfile.TarError as ex:
            raise CorruptArchive(str(ex)) from ex

    def test(self, tracker):
        problems = []
        try:
            with self._open() as tf:
                for ti in tf:
                    tracker.start_file(ti.name)
                    if ti.isreg():
                        f = tf.extractfile(ti)
                        while f:
                            c = f.read(1024 * 1024)
                            if not c:
                                break
                            tracker.add_bytes(len(c))
                    tracker.end_file()
        except (tarfile.TarError, OSError, EOFError, lzma.LZMAError) as ex:
            problems.append(str(ex))
        return problems


# ------------------------------------------------------------- single stream
class SingleReader(ArchiveReader):
    """.gz / .bz2 / .xz / .zst holding one file."""

    def __init__(self, path, source, password, encoding, kind: str):
        super().__init__(path, source, password, encoding)
        self.fmt = kind
        name = path.name
        name = re.sub(r"\.\d{3}$", "", name)
        out = re.sub(r"\.(gz|bz2|xz|zst|z)$", "", name, flags=re.I)
        if out == name:
            out = name + ".out"
        size = 0
        if kind == "gz" and self.packed_size >= 22:
            try:
                with open(path, "rb") as f:
                    f.seek(-4, os.SEEK_END)
                    size = int.from_bytes(f.read(4), "little")
            except OSError:
                pass
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            mtime = None
        self.entries.append(Entry(path=out, size=size, packed=self.packed_size, mtime=mtime,
                                  method=kind, index=0))
        self._est = size or self.packed_size * 4

    def estimated_total(self, entries):
        return self._est if entries else 0

    def _raw(self):
        if isinstance(self.source, Path):
            return open(self.source, "rb")
        self.source.seek(0)
        return self.source

    def open_member(self, entry: Entry) -> BinaryIO:
        raw = self._raw()
        k = self.fmt
        if k == "gz":
            return gzip.GzipFile(fileobj=raw)
        if k == "bz2":
            return bz2.BZ2File(raw)
        if k == "xz":
            return lzma.LZMAFile(raw)
        if k == "zst" and zstandard:
            return zstandard.ZstdDecompressor().stream_reader(raw)
        raise UnsupportedFormat(k)

    def extract(self, entries, sink):
        try:
            super().extract(entries, sink)
        except (OSError, EOFError, lzma.LZMAError) as ex:
            raise CorruptArchive(str(ex)) from ex


# ----------------------------------------------------------------------- 7z
class _Probe(Exception):
    pass


class SevenZipReader(ArchiveReader):
    fmt = "7z"

    def __init__(self, path, source, password, encoding):
        super().__init__(path, source, password, encoding)
        if py7zr is None:  # pragma: no cover
            raise UnsupportedFormat("py7zr missing")
        self.sz = None
        self._open()

    def _open(self):
        src = self.source if not isinstance(self.source, Path) else str(self.source)
        try:
            self.sz = py7zr.SevenZipFile(src, "r", password=self.password)
        except py7zr.exceptions.PasswordRequired as ex:
            raise PasswordRequired(str(ex)) from ex
        except Exception as ex:  # noqa: BLE001
            if "Password" in type(ex).__name__:
                raise PasswordRequired(str(ex)) from ex
            if self._header_encrypted():
                if self.password:
                    raise WrongPassword(str(ex)) from ex
                raise PasswordRequired(str(ex)) from ex
            raise CorruptArchive(str(ex)) from ex
        try:
            self.encrypted = bool(self.sz.needs_password())
        except Exception:  # noqa: BLE001
            self.encrypted = False
        for idx, f in enumerate(self.sz.files):
            name = f.filename.replace("\\", "/").strip("/")
            if not name:
                continue
            mtime = None
            try:
                if f.lastwritetime is not None:
                    from py7zr.helpers import filetime_to_dt
                    mtime = filetime_to_dt(f.lastwritetime).astimezone().replace(tzinfo=None)
            except Exception:  # noqa: BLE001
                mtime = None
            mode = None
            try:
                if f.is_unix_extension:
                    mode = stat.S_IMODE(f.st_fmt)
            except Exception:  # noqa: BLE001
                mode = None
            self.entries.append(Entry(
                path=name, is_dir=f.is_directory, size=f.uncompressed or 0, packed=-1,
                mtime=mtime, crc=getattr(f, "crc32", None), encrypted=self.encrypted and not f.is_directory,
                method="LZMA2/7z", mode=mode, is_link=bool(f.is_symlink), index=idx, raw=f.filename,
            ))

    def _header_encrypted(self) -> bool:
        """True when the (encoded) 7z header uses the AES coder."""
        try:
            f = open(self.source, "rb") if isinstance(self.source, Path) else self.source
            try:
                f.seek(12)
                off, size = struct.unpack("<QQ", f.read(16))
                if size <= 0 or size > 1 << 20:
                    return False
                f.seek(32 + off)
                return b"\x06\xf1\x07\x01" in f.read(size)
            finally:
                if isinstance(self.source, Path):
                    f.close()
        except (OSError, struct.error):
            return False

    def _reopen(self):
        self.sz.close()
        if isinstance(self.source, MultiVolumeFile):
            self.source.seek(0)
        self._reopen_open()

    def _reopen_open(self):
        src = self.source if not isinstance(self.source, Path) else str(self.source)
        self.sz = py7zr.SevenZipFile(src, "r", password=self.password)

    def _run(self, targets: Optional[List[str]], factory, dest: Path):
        self._reopen()
        try:
            self.sz.extract(path=str(dest), targets=targets, factory=factory)
        except _Probe:
            pass
        except Cancelled:
            raise
        except py7zr.exceptions.PasswordRequired as ex:
            raise PasswordRequired(str(ex)) from ex
        except (py7zr.exceptions.CrcError, lzma.LZMAError, py7zr.exceptions.UnsupportedCompressionMethodError) as ex:
            if self.encrypted:
                raise WrongPassword(str(ex)) from ex
            raise CorruptArchive(str(ex)) from ex
        except py7zr.exceptions.Bad7zFile as ex:
            raise CorruptArchive(str(ex)) from ex
        except Exception as ex:  # noqa: BLE001
            # exceptions raised inside worker threads may be wrapped
            cur = ex
            while cur is not None:
                if isinstance(cur, Cancelled):
                    raise cur from None
                cur = cur.__cause__ or cur.__context__
            if self.encrypted and "password" in str(ex).lower():
                raise WrongPassword(str(ex)) from ex
            raise CorruptArchive(str(ex)) from ex

    def open_member(self, entry: Entry) -> BinaryIO:
        factory = _MemFactory(limit=512 * 1024 * 1024)
        self._run([entry.raw], factory, Path(tempfile.gettempdir()))
        data = factory.data.get(entry.path)
        if data is None:
            data = next(iter(factory.data.values()), b"")
        return io.BytesIO(data)

    def verify_password(self) -> None:
        """Decrypt the first small file and compare its CRC (detects wrong passwords)."""
        if not self.encrypted:
            return
        files = [e for e in self.entries if not e.is_dir and e.size > 0]
        if not files:
            return
        pick = next((e for e in files if e.size <= _PROBE_MAX), files[0])
        probe = _ProbeFactory(pick.crc if pick.size <= _PROBE_MAX else None)
        self._run([pick.raw], probe, Path(tempfile.gettempdir()))
        if probe.ok is False:
            raise WrongPassword("CRC mismatch")

    def extract(self, entries, sink):
        files = [e for e in entries if not e.is_dir]
        for e in sorted((e for e in entries if e.is_dir), key=lambda x: x.index):
            sink.make_dir(e)
        if not files:
            return
        by_rel = {e.path: e for e in files}
        all_files = sum(1 for x in self.entries if not x.is_dir)
        targets = None if len(files) == all_files else [e.raw for e in files]
        self._run(targets, _SinkFactory(sink, by_rel, sink.root), sink.root)

    def close(self):
        if self.sz:
            self.sz.close()


class _DiscardIO(Py7zIO if py7zr else object):
    def __init__(self):
        self._n = 0

    def write(self, s):
        self._n += len(s)
        return len(s)

    def read(self, size=None):
        return b""

    def seek(self, offset, whence=0):
        return 0

    def flush(self):
        pass

    def size(self):
        return self._n


_PROBE_MAX = 64 * 1024 * 1024


class _ProbeIO(_DiscardIO):
    """Collects the CRC of one file, then aborts extraction via _Probe."""

    def __init__(self, owner, expected):
        super().__init__()
        self.owner, self.expected, self.crc = owner, expected, 0

    def write(self, s):
        self.crc = zlib.crc32(s, self.crc)
        return super().write(s)

    def close(self):
        if self.expected is not None:
            self.owner.ok = (self.crc & 0xFFFFFFFF) == self.expected
        raise _Probe()


class _ProbeFactory(WriterFactory if py7zr else object):
    def __init__(self, expected):
        self.expected = expected
        self.ok = None

    def create(self, filename):
        return _ProbeIO(self, self.expected)


class _MemIO(Py7zIO if py7zr else object):
    def __init__(self, buf: io.BytesIO, limit: int):
        self._b = buf
        self._limit = limit

    def write(self, s):
        if self._b.tell() + len(s) > self._limit:
            raise MemoryError("preview too large")
        return self._b.write(s)

    def read(self, size=None):
        return self._b.read() if size is None else self._b.read(size)

    def seek(self, offset, whence=0):
        return self._b.seek(offset, whence)

    def flush(self):
        pass

    def size(self):
        return len(self._b.getbuffer())


class _MemFactory(WriterFactory if py7zr else object):
    def __init__(self, limit):
        self.limit = limit
        self.data: dict = {}
        self._bufs: dict = {}

    def create(self, filename):
        buf = io.BytesIO()
        self._bufs[filename] = buf
        factory = self

        class _IO(_MemIO):
            def close(self_inner):
                factory.data[filename] = buf.getvalue()

        return _IO(buf, self.limit)


class _SinkFileIO(Py7zIO if py7zr else object):
    def __init__(self, sink: Sink, entry: Entry, target: Optional[Path], fh):
        self.sink, self.entry, self.target, self.fh = sink, entry, target, fh
        self._n = 0
        self._failed = False

    def write(self, s):
        self.sink.cancel.check()
        n = len(s)
        if self.fh is not None:
            self.fh.write(s)
            self.sink.result.bytes += n
        self._n += n
        self.sink.tracker.add_bytes(n)
        return n

    def read(self, size=None):
        return b""

    def seek(self, offset, whence=0):
        return 0

    def flush(self):
        pass

    def size(self):
        return self._n

    def close(self):
        if self.fh is not None:
            self.fh.close()
            self.fh = None
            if self.target is not None:
                self.sink.finish_file(self.target, self.entry)
        self.sink.tracker.end_file()


class _SinkFactory(WriterFactory if py7zr else object):
    def __init__(self, sink: Sink, by_rel: dict, root: Path):
        self.sink, self.by_rel, self.root = sink, by_rel, root

    def create(self, filename):
        rel = os.path.relpath(filename, self.root).replace("\\", "/")
        entry = self.by_rel.get(rel)
        if entry is None:
            entry = Entry(path=rel)
        self.sink.tracker.start_file(entry.path)
        opened = self.sink.open_target(entry)
        if opened is None:
            return _SinkFileIO(self.sink, entry, None, None)
        target, fh = opened
        return _SinkFileIO(self.sink, entry, target, fh)


# --------------------------------------------------- external 7-Zip (extended)
def find_7z() -> Optional[str]:
    env = os.environ.get("WARPZIP_7Z")
    cands: List[str] = [env] if env else []
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    exe_dir = Path(sys.executable).parent
    names = ["7z.exe", "7zz.exe", "7za.exe"] if sys.platform == "win32" else ["7zz", "7z", "7za", "7zr"]
    for base in (exe_dir / "bin", here / "bin", here / "warpzip" / "bin", exe_dir):
        for n in names:
            cands.append(str(base / n))
    if sys.platform == "win32":
        for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if pf:
                cands.append(str(Path(pf) / "7-Zip" / "7z.exe"))
    for c in cands:
        if c and Path(c).is_file():
            return c
    for n in names:
        w = shutil.which(n)
        if w:
            return w
    return None


class ExternalReader(ArchiveReader):
    """RAR, ISO, CAB, WIM, ARJ, LZH ... via a 7-Zip binary (optional)."""

    def __init__(self, path, source, password, encoding, kind: str):
        super().__init__(path, source, password, encoding)
        self.fmt = kind
        self.tool = find_7z()
        if not self.tool:
            raise ToolMissing(kind)
        self._joined: Optional[Path] = None
        self._archive = self._local_file()
        self._list()

    def _local_file(self) -> Path:
        if isinstance(self.source, Path):
            return self.source
        # multi-volume: join into a temp file for the CLI
        fd, tmp = tempfile.mkstemp(suffix="." + self.fmt, prefix="warpzip-join-")
        os.close(fd)
        self._joined = Path(tmp)
        self.source.seek(0)
        with open(tmp, "wb") as out:
            shutil.copyfileobj(self.source, out, 1024 * 1024)
        return self._joined

    def _cmd(self, *args: str, pw_via_stdin: bool = True) -> List[str]:
        cmd = [self.tool, *args]
        if self.password:
            cmd.insert(2, f"-p{self.password}")
        else:
            cmd.insert(2, "-p")  # empty pw: never block on a prompt
        return cmd

    def _popen(self, cmd, **kw):
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=flags, **kw)

    def _list(self):
        cmd = self._cmd("l", "-slt", "-ba", "-sccUTF-8", "-spd", "--", str(self._archive))
        p = self._popen(cmd)
        out = p.communicate()[0].decode("utf-8", errors="replace")
        low = out.lower()
        if p.returncode not in (0, 1):
            if "wrong password" in low or "encrypted" in low and self.password:
                raise WrongPassword(out[-200:])
            if "enter password" in low or "encrypted" in low:
                raise PasswordRequired(out[-200:])
            raise CorruptArchive(out[-300:])
        blocks = [b for b in re.split(r"\r?\n\r?\n", out) if b.strip()]
        idx = 0
        for b in blocks:
            kv = {}
            for line in b.splitlines():
                if " = " in line:
                    k, v = line.split(" = ", 1)
                    kv[k.strip()] = v.strip()
            if "Path" not in kv:
                continue
            name = kv["Path"].replace("\\", "/").strip("/")
            is_dir = kv.get("Folder") == "+" or kv.get("Attributes", "").startswith("D")
            mtime = None
            if kv.get("Modified"):
                try:
                    mtime = datetime.strptime(kv["Modified"][:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            crc = None
            if kv.get("CRC"):
                try:
                    crc = int(kv["CRC"], 16)
                except ValueError:
                    pass
            encrypted = kv.get("Encrypted") == "+"
            self.encrypted = self.encrypted or encrypted
            self.entries.append(Entry(
                path=name, is_dir=is_dir, size=int(kv.get("Size") or 0),
                packed=int(kv["Packed Size"]) if kv.get("Packed Size", "").isdigit() else -1,
                mtime=mtime, crc=crc, encrypted=encrypted, method=kv.get("Method", ""),
                index=idx,
            ))
            idx += 1

    def _extract_to(self, dest: Path, names: Optional[List[str]], tracker: Optional[ProgressTracker], total: int):
        cmd = self._cmd("x", "-y", "-aoa", "-bsp1", "-bso0", "-sccUTF-8", "-spd",
                        f"-o{dest}", "--", str(self._archive), *(names or []))
        p = self._popen(cmd)
        done = threading.Event()

        def watch():
            while not done.wait(0.1):
                if tracker and tracker.cancel.cancelled:
                    p.kill()
                    return

        t = threading.Thread(target=watch, daemon=True)
        t.start()
        tail = b""
        last = 0
        try:
            while True:
                chunk = p.stdout.read(128)
                if not chunk:
                    break
                tail = (tail + chunk)[-400:]
                if tracker:
                    ms = re.findall(rb"(\d{1,3})%", chunk)
                    if ms:
                        pct = min(100, int(ms[-1]))
                        cur = int(total * pct / 100)
                        if cur > last:
                            tracker.p.bytes_done = cur
                            last = cur
                            tracker.emit()
            p.wait()
        finally:
            done.set()
            if p.poll() is None:
                p.kill()
        if tracker:
            tracker.cancel.check()
        text = tail.decode("utf-8", errors="replace").lower()
        if p.returncode not in (0, 1):
            if "wrong password" in text:
                raise WrongPassword(text[-200:])
            raise CorruptArchive(text[-300:])

    def open_member(self, entry: Entry) -> BinaryIO:
        tmp = Path(tempfile.mkdtemp(prefix="warpzip-prev-"))
        try:
            self._extract_to(tmp, [entry.path], None, 0)
            f = next((p for p in tmp.rglob("*") if p.is_file()), None)
            data = f.read_bytes() if f else b""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return io.BytesIO(data)

    def extract(self, entries, sink):
        names = None
        if len(entries) != len(self.entries):
            names = [e.path for e in entries]
        tmp = Path(tempfile.mkdtemp(prefix=".warpzip-", dir=str(sink.root)))
        try:
            total = sum(e.size for e in entries if not e.is_dir)
            self._extract_to(tmp, names, sink.tracker, total)
            for e in sorted(entries, key=lambda x: x.index):
                sink.cancel.check()
                if e.is_dir:
                    sink.make_dir(e)
                    continue
                src = tmp.joinpath(*e.path.split("/"))
                if src.is_file():
                    sink.adopt(e, src)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def close(self):
        if self._joined:
            self._joined.unlink(missing_ok=True)

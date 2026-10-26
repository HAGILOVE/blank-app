"""Format registry and content sniffing."""
from __future__ import annotations

import bz2
import gzip
import lzma
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

try:  # optional but listed in requirements
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None


@dataclass(frozen=True)
class FormatInfo:
    key: str
    label: str
    ext: str                       # canonical extension incl. dot
    can_write: bool = False
    password: bool = False         # supports encryption when writing
    header_encrypt: bool = False
    levels: bool = True
    native: bool = True            # handled without external 7-Zip


FORMATS = {f.key: f for f in (
    FormatInfo("zip", "ZIP", ".zip", True, True),
    FormatInfo("7z", "7Z", ".7z", True, True, True),
    FormatInfo("tar", "TAR", ".tar", True, levels=False),
    FormatInfo("tar.gz", "TAR.GZ", ".tar.gz", True),
    FormatInfo("tar.bz2", "TAR.BZ2", ".tar.bz2", True),
    FormatInfo("tar.xz", "TAR.XZ", ".tar.xz", True),
    FormatInfo("tar.zst", "TAR.ZST", ".tar.zst", True),
    FormatInfo("gz", "GZ", ".gz"),
    FormatInfo("bz2", "BZ2", ".bz2"),
    FormatInfo("xz", "XZ", ".xz"),
    FormatInfo("zst", "ZST", ".zst"),
    # read-only through the optional 7-Zip engine
    FormatInfo("rar", "RAR", ".rar", native=False),
    FormatInfo("iso", "ISO", ".iso", native=False),
    FormatInfo("cab", "CAB", ".cab", native=False),
    FormatInfo("wim", "WIM", ".wim", native=False),
    FormatInfo("arj", "ARJ", ".arj", native=False),
    FormatInfo("lzh", "LZH", ".lzh", native=False),
    FormatInfo("cpio", "CPIO", ".cpio", native=False),
    FormatInfo("rpm", "RPM", ".rpm", native=False),
    FormatInfo("deb", "DEB", ".deb", native=False),
    FormatInfo("z", "Z", ".z", native=False),
    FormatInfo("vhd", "VHD", ".vhd", native=False),
    FormatInfo("dmg", "DMG", ".dmg", native=False),
    FormatInfo("chm", "CHM", ".chm", native=False),
)}

WRITABLE = [f for f in FORMATS.values() if f.can_write]

# extension -> format key (longest first when matching)
_EXT = {
    ".zip": "zip", ".zipx": "zip", ".jar": "zip", ".war": "zip", ".apk": "zip",
    ".whl": "zip", ".epub": "zip", ".xpi": "zip", ".egg": "zip",
    ".7z": "7z",
    ".tar": "tar", ".tar.gz": "tar.gz", ".tgz": "tar.gz", ".tar.bz2": "tar.bz2",
    ".tbz": "tar.bz2", ".tbz2": "tar.bz2", ".tar.xz": "tar.xz", ".txz": "tar.xz",
    ".tar.zst": "tar.zst", ".tzst": "tar.zst",
    ".gz": "gz", ".bz2": "bz2", ".xz": "xz", ".zst": "zst",
    ".rar": "rar", ".iso": "iso", ".cab": "cab", ".wim": "wim", ".swm": "wim",
    ".arj": "arj", ".lzh": "lzh", ".lha": "lzh", ".cpio": "cpio", ".rpm": "rpm",
    ".deb": "deb", ".z": "z", ".vhd": "vhd", ".vhdx": "vhd", ".dmg": "dmg",
    ".chm": "chm",
}

#: extensions WARPZIP offers to associate with itself in Windows
ASSOCIABLE = (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst",
              ".iso", ".cab", ".wim", ".arj", ".lzh", ".001")

ARCHIVE_EXTENSIONS = tuple(sorted(_EXT, key=len, reverse=True))


def format_by_name(name: str) -> Optional[str]:
    low = name.lower()
    for ext in ARCHIVE_EXTENSIONS:
        if low.endswith(ext):
            return _EXT[ext]
    return None


def archive_stem(name: str) -> str:
    """'photos.tar.gz' -> 'photos', 'big.zip.001' -> 'big'."""
    import re

    n = re.sub(r"\.\d{3}$", "", name)
    low = n.lower()
    for ext in ARCHIVE_EXTENSIONS:
        if low.endswith(ext) and len(n) > len(ext):
            return n[: -len(ext)]
    return Path(n).stem or n


def _is_tar_header(block: bytes) -> bool:
    return len(block) >= 262 and block[257:262] == b"ustar"


def _peek_decompressed(stream: BinaryIO, kind: str, n: int = 512) -> bytes:
    stream.seek(0)
    try:
        if kind == "gz":
            return gzip.GzipFile(fileobj=stream).read(n)
        if kind == "bz2":
            return bz2.BZ2File(stream).read(n)
        if kind == "xz":
            return lzma.LZMAFile(stream).read(n)
        if kind == "zst" and zstandard:
            return zstandard.ZstdDecompressor().stream_reader(stream).read(n)
    except Exception:
        return b""
    return b""


def sniff(stream: BinaryIO, name_hint: str = "") -> Optional[str]:
    """Detect the archive format from content (falling back to the name)."""
    stream.seek(0)
    head = stream.read(512)
    stream.seek(0)
    key: Optional[str] = None
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        key = "zip"
    elif head[:6] == b"7z\xbc\xaf\x27\x1c":
        key = "7z"
    elif head[:6] == b"Rar!\x1a\x07":
        key = "rar"
    elif head[:2] == b"\x1f\x8b":
        key = "gz"
    elif head[:3] == b"BZh":
        key = "bz2"
    elif head[:6] == b"\xfd7zXZ\x00":
        key = "xz"
    elif head[:4] == b"\x28\xb5\x2f\xfd":
        key = "zst"
    elif _is_tar_header(head):
        key = "tar"
    elif head[:4] == b"MSCF":
        key = "cab"
    elif head[:5] == b"MSWIM":
        key = "wim"
    elif head[:2] == b"\x60\xea":
        key = "arj"
    elif head[2:5] == b"-lh" or head[2:5] == b"-lz":
        key = "lzh"
    elif head[:2] == b"\x1f\x9d":
        key = "z"
    elif head[:6] in (b"070707", b"070701", b"070702"):
        key = "cpio"
    elif head[:4] == b"\xed\xab\xee\xdb":
        key = "rpm"
    elif head[:8] == b"!<arch>\n":
        key = "deb"
    elif head[:4] == b"ITSF":
        key = "chm"
    else:
        stream.seek(0x8000)
        if stream.read(6)[1:6] == b"CD001":
            key = "iso"
        stream.seek(0)
    if key in ("gz", "bz2", "xz", "zst"):
        inner = _peek_decompressed(stream, key)
        stream.seek(0)
        if _is_tar_header(inner):
            key = {"gz": "tar.gz", "bz2": "tar.bz2", "xz": "tar.xz", "zst": "tar.zst"}[key]
    if key is None:
        key = format_by_name(name_hint)
    return key


def sniff_path(path: Path) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return sniff(f, path.name)
    except OSError:
        return format_by_name(path.name)


def is_archive_name(name: str) -> bool:
    import re

    return format_by_name(re.sub(r"\.\d{3}$", "", name)) is not None or bool(
        re.search(r"\.001$", name)
    )

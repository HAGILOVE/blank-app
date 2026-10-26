"""Recover non-UTF-8 file names (Korean cp949, Japanese cp932, Chinese gbk/big5).

Old ZIP tools (AlZip, WinZip, Windows Explorer < 11) store names in the local
ANSI code page without setting the UTF-8 flag.  Python decodes those as cp437,
producing mojibake.  We re-encode with cp437 to get the raw bytes back and
decode them again with the best candidate.
"""
from __future__ import annotations

import locale
import re
from typing import Iterable, Optional

CANDIDATES = ("cp949", "cp932", "gbk", "big5")   # auto-detect pool (others: manual)

#: user-selectable encodings (label, codec)
CHOICES = (
    ("auto", "auto"),
    ("UTF-8", "utf-8"),
    ("한국어 (CP949)", "cp949"),
    ("日本語 (Shift-JIS)", "cp932"),
    ("简体中文 (GBK)", "gbk"),
    ("繁體中文 (Big5)", "big5"),
    ("Русский (CP866)", "cp866"),
    ("Русский (CP1251)", "cp1251"),
    ("Western (CP1252)", "cp1252"),
    ("DOS (CP437)", "cp437"),
)

_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_KANA = re.compile(r"[぀-ヿ]")
_HAN = re.compile(r"[一-鿿]")
_CYR = re.compile(r"[Ѐ-ӿ]")


def _score(raw: bytes, text: str, codec: str) -> float:
    """Plausibility 0..1 that *text* (decoded from *raw*) is natural language."""
    chars = [c for c in text if ord(c) > 127]
    if not chars:
        return 0.0
    if "\ufffd" in text:
        return -1.0
    n = len(chars)
    if codec == "cp949":
        ratio = sum(1 for c in chars if _HANGUL.match(c)) / n
        try:
            raw.decode("euc-kr")          # strict KS X 1001 only: no rare extensions
            return ratio
        except UnicodeDecodeError:
            return ratio * 0.6            # kana mis-read as extended Hangul lands here
    if codec == "cp932":
        kana = sum(1 for c in chars if _KANA.match(c))
        han = sum(1 for c in chars if _HAN.match(c))
        half = sum(1 for c in chars if "\uff61" <= c <= "\uff9f")
        return min(1.0, (kana * 1.0 + han * 0.9 + half * 0.2) / n)
    if codec in ("gbk", "big5"):
        return 0.9 * sum(1 for c in chars if _HAN.match(c)) / n
    if codec == "cp1251":
        return sum(1 for c in chars if _CYR.match(c)) / n
    return 0.05


def _preferred_order() -> tuple[str, ...]:
    lang = (locale.getlocale()[0] or "").lower()
    order = list(CANDIDATES)
    for key, codec in (("korean", "cp949"), ("ko", "cp949"), ("japan", "cp932"),
                       ("ja", "cp932"), ("chinese", "gbk"), ("zh", "gbk")):
        if lang.startswith(key):
            order.remove(codec)
            order.insert(0, codec)
            break
    return tuple(order)


def is_ascii(b: bytes) -> bool:
    return all(c < 0x80 for c in b)


def detect_encoding(samples: Iterable[bytes]) -> str:
    """Pick the most plausible legacy codec for the given raw names."""
    raws = [s for s in samples if s and not is_ascii(s)]
    if not raws:
        return "utf-8"
    # Valid UTF-8 for every sample => it *is* UTF-8 (flag simply missing).
    try:
        for r in raws:
            r.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    best, best_score = "cp437", -2.0
    for rank, codec in enumerate(_preferred_order()):
        total, ok = 0.0, True
        for r in raws:
            try:
                total += _score(r, r.decode(codec), codec)
            except UnicodeDecodeError:
                ok = False
                break
        if not ok:
            continue
        avg = total / len(raws) - rank * 0.001  # tie-break by locale preference
        if avg > best_score:
            best, best_score = codec, avg
    return best


def decode_name(raw: bytes, codec: str) -> str:
    try:
        return raw.decode(codec)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def zip_raw_name(orig_filename: str, flag_bits: int) -> Optional[bytes]:
    """Raw name bytes of a ZIP entry that was *not* flagged UTF-8, else None."""
    if flag_bits & 0x800:
        return None
    try:
        return orig_filename.encode("cp437")
    except UnicodeEncodeError:
        return None


def parse_unicode_path_extra(extra: bytes, raw_name: bytes) -> Optional[str]:
    """Info-ZIP Unicode Path Extra Field (0x7075) -> UTF-8 name if CRC matches."""
    import zlib

    i = 0
    while i + 4 <= len(extra):
        hid = int.from_bytes(extra[i:i + 2], "little")
        size = int.from_bytes(extra[i + 2:i + 4], "little")
        body = extra[i + 4:i + 4 + size]
        if hid == 0x7075 and len(body) >= 5 and body[0] == 1:
            crc = int.from_bytes(body[1:5], "little")
            if crc == (zlib.crc32(raw_name) & 0xFFFFFFFF):
                try:
                    return body[5:].decode("utf-8")
                except UnicodeDecodeError:
                    return None
        i += 4 + size
    return None

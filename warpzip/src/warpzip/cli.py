"""Command line interface:  warpzip a|x|e|l|t|h ...

Usable from scripts and from a terminal (`wz.exe`).  Exit codes:
0 ok · 1 error · 2 usage · 3 password · 130 cancelled
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import APP_NAME, __version__
from .core.archive import analyze, extract, open_archive, verify_archive
from .core.compress import DEFAULT_EXCLUDES, CompressOptions, compress
from .core.errors import (
    Cancelled, CorruptArchive, PasswordRequired, UnsupportedFormat, WarpError, WrongPassword,
)
from .core.formats import FORMATS, format_by_name
from .core.fsutil import human_size
from .core.hashing import hash_file
from .core.progress import Progress
from .core.sink import ExtractOptions

COMMANDS = {"a", "add", "x", "extract", "e", "l", "list", "t", "test", "h", "hash"}


def attach_console() -> None:
    """A windowed (GUI) exe has no console; attach the parent's so output is visible."""
    if sys.platform != "win32" or sys.stdout is not None and sys.stdout.isatty():
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:  # noqa: BLE001
        pass


class Bar:
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self.last = 0.0

    def __call__(self, p: Progress) -> None:
        if self.quiet or not sys.stdout:
            return
        now = time.monotonic()
        if now - self.last < 0.1 and p.fraction < 1:
            return
        self.last = now
        w = 24
        n = int(p.fraction * w)
        line = f"[{'#' * n}{'.' * (w - n)}] {p.fraction * 100:3.0f}%  {human_size(p.speed):>9}/s  {p.current[-40:]}"
        sys.stdout.write("\r" + line.ljust(78))
        sys.stdout.flush()

    def done(self) -> None:
        if not self.quiet and sys.stdout:
            sys.stdout.write("\r" + " " * 78 + "\r")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="warpzip", description=f"{APP_NAME} {__version__} - command line")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("a", aliases=["add"], help="create an archive")
    a.add_argument("archive")
    a.add_argument("files", nargs="+")
    a.add_argument("-f", "--format", choices=[k for k, f in FORMATS.items() if f.can_write])
    a.add_argument("-l", "--level", type=int, default=5, choices=range(0, 10), metavar="0-9")
    a.add_argument("-p", "--password")
    a.add_argument("--encrypt-names", action="store_true", help="7z: also encrypt file names")
    a.add_argument("--split", metavar="SIZE", help="volume size, e.g. 100m, 4g")
    a.add_argument("-x", "--exclude", action="append", default=[], help="pattern to skip (repeatable)")
    a.add_argument("--no-smart-store", action="store_true")
    a.add_argument("-q", "--quiet", action="store_true")

    for name, alias in (("x", "extract"), ("e", None)):
        x = sub.add_parser(name, aliases=[alias] if alias else [], help="extract" + (" without folders" if name == "e" else ""))
        x.add_argument("archive")
        x.add_argument("-o", "--output", default=None)
        x.add_argument("-p", "--password")
        x.add_argument("--folder", choices=["smart", "always", "never"], default="never" if name == "e" else "smart")
        x.add_argument("--overwrite", choices=["overwrite", "skip", "rename", "newer"], default="rename")
        x.add_argument("--encoding", help="file name code page, e.g. cp949")
        x.add_argument("-q", "--quiet", action="store_true")

    l = sub.add_parser("l", aliases=["list"], help="list contents")
    l.add_argument("archive")
    l.add_argument("-p", "--password")
    l.add_argument("--encoding")

    t = sub.add_parser("t", aliases=["test"], help="test integrity")
    t.add_argument("archive")
    t.add_argument("-p", "--password")
    t.add_argument("-q", "--quiet", action="store_true")

    h = sub.add_parser("h", aliases=["hash"], help="print checksums")
    h.add_argument("file")
    return p


def parse_size(txt: str) -> int:
    t = txt.strip().lower()
    mult = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    if t and t[-1] in mult:
        return int(float(t[:-1]) * mult[t[-1]])
    if t.endswith("b"):
        t = t[:-1]
    return int(float(t))


def run(argv: Optional[List[str]] = None) -> int:
    attach_console()
    ns = build_parser().parse_args(argv)
    cmd = ns.cmd
    try:
        if cmd in ("a", "add"):
            fmt = ns.format or format_by_name(ns.archive) or "zip"
            if fmt not in FORMATS or not FORMATS[fmt].can_write:
                print(f"error: cannot create '{fmt}' archives", file=sys.stderr)
                return 2
            opts = CompressOptions(
                fmt=fmt, level=ns.level, password=ns.password, encrypt_names=ns.encrypt_names,
                split_size=parse_size(ns.split) if ns.split else 0,
                exclude=DEFAULT_EXCLUDES + ns.exclude, smart_store=not ns.no_smart_store,
            )
            bar = Bar(ns.quiet)
            res = compress([Path(f) for f in ns.files], Path(ns.archive), opts, bar)
            bar.done()
            print(f"OK  {res.files} files, {human_size(res.original)} -> {human_size(res.packed)} "
                  f"({res.ratio * 100:.0f}% saved)  {res.outputs[0].name}" + (f" (+{len(res.outputs) - 1} parts)" if len(res.outputs) > 1 else ""))
            return 0
        if cmd in ("x", "extract", "e"):
            with open_archive(ns.archive, ns.password, ns.encoding) as rd:
                if rd.encrypted:
                    rd.verify_password()
                dest = Path(ns.output) if ns.output else Path(ns.archive).resolve().parent
                bar = Bar(ns.quiet)
                res = extract(rd, dest, None, ExtractOptions(folder_mode=ns.folder, overwrite=ns.overwrite), bar)
                bar.done()
            print(f"OK  {res.files} files ({human_size(res.bytes)}) -> {res.root}")
            for u in res.unsafe:
                print(f"blocked unsafe path: {u}", file=sys.stderr)
            return 0
        if cmd in ("l", "list"):
            with open_archive(ns.archive, ns.password, ns.encoding) as rd:
                for e in rd.entries:
                    when = e.mtime.strftime("%Y-%m-%d %H:%M") if e.mtime else " " * 16
                    print(f"{when}  {'D' if e.is_dir else ' '}{'*' if e.encrypted else ' '} {e.size:>12,}  {e.path}")
                st = analyze(rd)
                print(f"--\n{st.files} files, {st.dirs} folders, {human_size(st.total_size)} "
                      f"({human_size(rd.packed_size)} packed, {st.ratio * 100:.0f}% saved)")
            return 0
        if cmd in ("t", "test"):
            with open_archive(ns.archive, ns.password) as rd:
                if rd.encrypted:
                    rd.verify_password()
                bar = Bar(ns.quiet)
                problems = verify_archive(rd, bar)
                bar.done()
            if problems:
                print("FAILED", *problems, sep="\n  ", file=sys.stderr)
                return 1
            print("OK  everything is fine")
            return 0
        if cmd in ("h", "hash"):
            for k, v in hash_file(ns.file).items():
                print(f"{k:8} {v}")
            return 0
    except (PasswordRequired, WrongPassword) as ex:
        print(f"error: password required or wrong ({ex})", file=sys.stderr)
        return 3
    except Cancelled:
        return 130
    except (CorruptArchive, UnsupportedFormat, WarpError, OSError) as ex:
        print(f"error: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 1
    return 2

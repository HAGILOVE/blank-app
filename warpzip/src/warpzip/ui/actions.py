"""High-level user actions shared by the main window and the shell quick-actions.

Every action asks the user what it needs, runs the engine in a worker thread and
turns exceptions into friendly Warpy messages.
"""
from __future__ import annotations

import errno
import subprocess
import sys
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ..core import archive as ar
from ..core.archive import analyze, open_archive
from ..core.compress import CompressOptions, CompressResult, compress
from ..core.edit import edit_zip
from ..core.entry import Entry
from ..core.errors import (
    CorruptArchive, DiskSpaceError, PasswordRequired, ToolMissing, UnsupportedFormat, WrongPassword,
)
from ..core.formats import FORMATS, archive_stem, sniff_path
from ..core.fsutil import human_size, move_to_recycle_bin
from ..core.readers import ArchiveReader
from ..core.repair import repair_zip
from ..core.security import unique_path
from ..core.sink import ExtractOptions, ExtractResult
from ..core.volumes import volume_parts
from ..settings import Settings
from .compress_dialog import CompressDialog
from .dialogs import ask_password, confirm, message
from .extract_dialog import EXEC_EXT, ExtractDialog
from .i18n import tr
from .progress_dialog import run_job


def reveal(path: Path) -> None:
    """Show *path* in Explorer (selected when possible)."""
    path = Path(path)
    if sys.platform == "win32" and path.exists():
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))


def open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def describe_error(ex: BaseException) -> tuple[str, str]:
    if isinstance(ex, (PasswordRequired, WrongPassword)):
        return tr("비밀번호가 맞지 않아요", "Wrong password"), tr("비밀번호를 다시 확인해 주세요.", "Please check the password.")
    if isinstance(ex, CorruptArchive):
        return (tr("압축 파일이 손상된 것 같아요", "The archive looks damaged"),
                tr("다운로드가 중간에 끊겼거나 파일이 깨졌을 수 있어요. 다시 받아 보세요.\n\n", "The download may be incomplete or the file corrupted.\n\n") + str(ex))
    if isinstance(ex, UnsupportedFormat):
        return (tr("열 수 없는 파일이에요", "Can't open this file"),
                tr("압축 파일이 아니거나 아직 지원하지 않는 형식이에요.", "Not an archive, or a format that isn't supported yet."))
    if isinstance(ex, ToolMissing):
        return (tr("확장 엔진이 필요해요", "Extension engine needed"),
                tr("RAR·ISO·CAB 같은 형식을 열려면 7-Zip 엔진(7z.exe)이 필요해요.\n설치 폴더의 bin 폴더에 7z.exe와 7z.dll을 넣거나 7-Zip을 설치하세요.",
                   "RAR/ISO/CAB need the 7-Zip engine (7z.exe).\nPlace 7z.exe and 7z.dll in the bin folder or install 7-Zip."))
    if isinstance(ex, DiskSpaceError):
        try:
            need, free = (int(x) for x in str(ex).split(":"))
            msg = tr(f"필요한 공간: {human_size(need)}\n남은 공간: {human_size(free)}", f"Needed: {human_size(need)}\nFree: {human_size(free)}")
        except ValueError:
            msg = ""
        return tr("저장 공간이 부족해요", "Not enough disk space"), msg
    if isinstance(ex, PermissionError):
        return (tr("접근할 수 없어요", "Access denied"),
                tr("파일이 다른 프로그램에서 사용 중이거나 권한이 없어요.\n", "The file is in use or you lack permission.\n") + str(ex))
    if isinstance(ex, OSError) and ex.errno == errno.ENOSPC:
        return tr("저장 공간이 부족해요", "Not enough disk space"), str(ex)
    if isinstance(ex, FileNotFoundError):
        return tr("파일을 찾을 수 없어요", "File not found"), str(ex)
    if isinstance(ex, MemoryError):
        return tr("메모리가 부족해요", "Out of memory"), ""
    return tr("앗, 문제가 생겼어요", "Oops, something went wrong"), f"{type(ex).__name__}: {ex}"


@dataclass
class ExtractOutcome:
    result: ExtractResult
    reader_closed: bool = False


class Actions:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.pw_cache: Dict[str, str] = {}
        self._temp_dirs: List[Path] = []

    # ---- errors ---------------------------------------------------------------------
    def show_error(self, parent, ex: BaseException) -> None:
        title, text = describe_error(ex)
        message(parent, "error", title, text)

    # ---- opening ------------------------------------------------------------------------
    def open_reader(self, parent, path: Path, encoding: Optional[str] = None) -> Optional[ArchiveReader]:
        path = Path(path)
        pw = self.pw_cache.get(str(path))
        wrong = False
        while True:
            out = run_job(parent, tr("압축 파일 여는 중", "Opening archive"), path.name,
                          lambda cb, cancel, pw=pw: open_archive(path, pw, encoding))
            if out.ok:
                return out.result
            if out.status == "cancelled":
                return None
            if isinstance(out.error, (PasswordRequired, WrongPassword)):
                wrong = wrong or isinstance(out.error, WrongPassword) or pw is not None
                r = ask_password(parent, path.name, wrong)
                if not r:
                    return None
                pw = r[0]
                if r[1]:
                    self.pw_cache[str(path)] = pw
                continue
            if isinstance(out.error, CorruptArchive) and (path.suffix.lower() == ".zip" or sniff_path(path) == "zip"):
                i = message(parent, "error", tr("압축 파일이 손상됐어요", "The archive is damaged"),
                            tr("파일 끝이 잘렸거나 손상된 것 같아요.\n멀쩡한 파일만 골라서 새 ZIP으로 복구해 볼까요?",
                               "The end of the file looks damaged or truncated.\nTry to rescue the intact files into a new ZIP?"),
                            buttons=[(tr("취소", "Cancel"), "normal"), (tr("복구하기", "Repair"), "primary")])
                if i == 1:
                    fixed = self.repair(parent, path)
                    if fixed:
                        return self.open_reader(parent, fixed, encoding)
                return None
            self.show_error(parent, out.error)
            return None

    def repair(self, parent, path: Path) -> Optional[Path]:
        dest = unique_path(Path(path).with_name(Path(path).stem + "_repaired.zip"))
        out = run_job(parent, tr("복구하는 중", "Repairing"), Path(path).name,
                      lambda cb, cancel: repair_zip(path, dest, cb, cancel), auto_close=True)
        if out.status == "cancelled":
            return None
        if not out.ok:
            self.show_error(parent, out.error)
            return None
        res = out.result
        if res.recovered == 0:
            dest.unlink(missing_ok=True)
            message(parent, "error", tr("복구할 수 있는 파일이 없어요", "Nothing could be rescued"),
                    tr("안타깝게도 온전한 파일을 찾지 못했어요.", "Sadly no intact files were found."), details="\n".join(res.failed[:100]))
            return None
        message(parent, "success", tr("복구했어요!", "Rescued!"),
                tr(f"{res.recovered:,}개 파일을 새 압축 파일로 구했어요.\n저장: {dest.name}", f"Recovered {res.recovered:,} files into {dest.name}") +
                (tr(f"\n구하지 못한 항목 {len(res.failed)}개", f"\n{len(res.failed)} items could not be saved") if res.failed else ""),
                details="\n".join(res.failed[:100]))
        return dest

    def ensure_password(self, parent, reader: ArchiveReader) -> bool:
        """Make sure data can be decrypted; asks for the password when needed."""
        if not reader.encrypted:
            return True
        key = str(reader.path)
        pw = reader.password or self.pw_cache.get(key)
        wrong = False
        while True:
            if pw is None:
                r = ask_password(parent, reader.path.name, wrong)
                if not r:
                    return False
                pw = r[0]
                if r[1]:
                    self.pw_cache[key] = pw
            reader.set_password(pw)
            out = run_job(parent, tr("비밀번호 확인 중", "Checking password"), reader.path.name,
                          lambda cb, cancel: reader.verify_password(), quick_ms=400)
            if out.ok:
                return True
            if isinstance(out.error, (WrongPassword, PasswordRequired)):
                pw, wrong = None, True
                self.pw_cache.pop(key, None)
                continue
            if out.status == "cancelled":
                return False
            self.show_error(parent, out.error)
            return False

    # ---- extract -----------------------------------------------------------------------------
    def extract(self, parent, reader: ArchiveReader, entries: Optional[Sequence[Entry]] = None,
                dest: Optional[Path] = None, opts: Optional[ExtractOptions] = None, ask: bool = True,
                strip_prefix: str = "", selected: int = 0, post: bool = True) -> Optional[ExtractOutcome]:
        entries = list(entries) if entries is not None else list(reader.entries)
        if not entries:
            return None
        if not self.ensure_password(parent, reader):
            return None
        stats = analyze(reader)
        if stats.suspicious:
            if not confirm(parent, tr("용량이 아주 커질 수 있어요", "This could be huge"),
                           tr(f"압축 파일 크기는 {human_size(reader.packed_size)}인데 풀면 {human_size(stats.total_size)}가 돼요.\n"
                              "'압축 폭탄'일 수 있으니 믿을 수 있는 파일일 때만 계속하세요.",
                              f"The archive is {human_size(reader.packed_size)} but expands to {human_size(stats.total_size)}.\n"
                              "It may be a 'zip bomb' - continue only if you trust it."),
                           tr("그래도 풀기", "Extract anyway"), danger=True):
                return None
        files = [e for e in entries if not e.is_dir]
        size = sum(e.size for e in files)
        open_after = self.s.get("extract/open_folder")
        del_after = False
        if opts is None:
            opts = ExtractOptions(folder_mode=self.s.get("extract/folder_mode"),
                                  overwrite=self.s.get("extract/overwrite"),
                                  propagate_motw=self.s.get("extract/motw"))
        opts.strip_prefix = strip_prefix
        if ask:
            has_exec = any(e.name.rsplit(".", 1)[-1].lower() in EXEC_EXT for e in files if "." in e.name)
            dlg = ExtractDialog(parent, reader.path, self.s, len(files), size, reader.encrypted, selected,
                                has_exec, reader.detected_encoding, reader.fmt == "zip")
            if dlg.exec() != dlg.Accepted:
                return None
            dest = dlg.destination()
            new = dlg.options()
            new.strip_prefix = strip_prefix
            opts = new
            open_after, del_after = dlg.open_after.isChecked(), dlg.del_after.isChecked()
            if new.encoding and new.encoding != (reader.encoding or reader.detected_encoding):
                if reader.fmt == "zip":                      # re-read names with the chosen code page
                    fresh = open_archive(reader.path, reader.password, new.encoding)
                    by_idx = {e.index: e for e in fresh.entries}
                    entries = [by_idx.get(e.index, e) for e in entries]
                    reader.close()
                    reader = fresh
        dest = Path(dest or reader.path.parent)

        def summary(res: ExtractResult):
            lines = [tr(f"{res.files:,}개 파일 ({human_size(res.bytes)})을 풀었어요.", f"Extracted {res.files:,} files ({human_size(res.bytes)}).")]
            if res.skipped:
                lines.append(tr(f"건너뜀 {len(res.skipped):,}개", f"Skipped {len(res.skipped):,}"))
            if res.unsafe:
                lines.append(tr(f"⚠ 안전하지 않은 경로 {len(res.unsafe):,}개는 차단했어요", f"⚠ Blocked {len(res.unsafe):,} unsafe paths"))
            return "\n".join(lines), [(tr("폴더 열기", "Open folder"), lambda: open_folder(res.root))]

        out = run_job(parent, tr("압축 푸는 중", "Extracting"), reader.path.name,
                      lambda cb, cancel: ar.extract(reader, dest, entries, opts, cb, cancel),
                      summary=None if (open_after or self.s.get("ui/auto_close_progress")) else summary,
                      auto_close=bool(open_after or self.s.get("ui/auto_close_progress")))
        if out.status == "cancelled":
            message(parent, "info", tr("취소했어요", "Cancelled"), tr("압축 풀기를 취소했어요. 일부 파일은 이미 풀렸을 수 있어요.", "Extraction cancelled. Some files may already exist."))
            return None
        if not out.ok:
            self.show_error(parent, out.error)
            return None
        res: ExtractResult = out.result
        if res.unsafe and (open_after or self.s.get("ui/auto_close_progress")):
            message(parent, "warning", tr("위험한 파일 경로를 막았어요", "Unsafe paths blocked"),
                    tr(f"압축 파일 안에 폴더 밖으로 빠져나가려는 경로가 {len(res.unsafe)}개 있어서 풀지 않았어요.", f"{len(res.unsafe)} entries tried to escape the folder and were skipped."),
                    details="\n".join(res.unsafe[:50]))
        closed = False
        if post:
            if del_after:
                reader.close()
                closed = True
                parts = volume_parts(reader.path) or [reader.path]
                if not move_to_recycle_bin(parts):
                    message(parent, "info", tr("휴지통으로 보내지 못했어요", "Couldn't recycle"), tr("압축 파일은 그대로 두었어요.", "The archive was left in place."))
            if open_after:
                open_folder(res.root)
        return ExtractOutcome(res, closed)

    # ---- compress --------------------------------------------------------------------------------
    def compress_dialog(self, parent, sources: Sequence[Path], default_dir: Optional[Path] = None,
                        default_name: str = "") -> Optional[CompressResult]:
        dlg = CompressDialog(parent, [Path(s) for s in sources], self.s, default_dir, default_name)
        if dlg.exec() != dlg.Accepted:
            return None
        return self.run_compress(parent, dlg.sources, dlg.destination(), dlg.options())

    def run_compress(self, parent, sources: Sequence[Path], dest: Path, opts: CompressOptions,
                     show_summary: bool = True) -> Optional[CompressResult]:
        def summary(res: CompressResult):
            first = res.outputs[0]
            txt = tr(f"{res.files:,}개 파일을 {human_size(res.original)} → {human_size(res.packed)}로 줄였어요! ({res.ratio*100:.0f}% 절약)",
                     f"Packed {res.files:,} files {human_size(res.original)} → {human_size(res.packed)} ({res.ratio*100:.0f}% saved)")
            if len(res.outputs) > 1:
                txt += tr(f"\n{len(res.outputs)}개 조각으로 나누었어요.", f"\nSplit into {len(res.outputs)} volumes.")
            if res.skipped:
                txt += tr(f"\n건너뜀 {len(res.skipped)}개", f"\nSkipped {len(res.skipped)}")
            return txt, [(tr("폴더에서 보기", "Show in folder"), lambda: reveal(first))]

        out = run_job(parent, tr("압축하는 중", "Compressing"), dest.name,
                      lambda cb, cancel: compress(sources, dest, opts, cb, cancel),
                      summary=summary if show_summary and not self.s.get("ui/auto_close_progress") else None,
                      auto_close=self.s.get("ui/auto_close_progress"))
        if out.status == "cancelled":
            return None
        if not out.ok:
            self.show_error(parent, out.error)
            return None
        return out.result

    # ---- test ---------------------------------------------------------------------------------------
    def test(self, parent, reader: ArchiveReader) -> None:
        if not self.ensure_password(parent, reader):
            return
        out = run_job(parent, tr("무결성 검사 중", "Testing integrity"), reader.path.name,
                      lambda cb, cancel: ar.verify_archive(reader, cb, cancel))
        if out.status == "cancelled":
            return
        if not out.ok:
            self.show_error(parent, out.error)
            return
        problems = out.result
        if problems:
            message(parent, "error", tr("문제가 발견됐어요", "Problems found"),
                    tr(f"{len(problems)}개 파일에 문제가 있어요.", f"{len(problems)} files have problems."), details="\n".join(problems[:200]))
        else:
            message(parent, "success", tr("이상 없어요!", "All good!"), tr("모든 파일이 깨끗하게 확인됐어요.", "Every file checked out fine."))

    # ---- editing (ZIP) -------------------------------------------------------------------------------
    def edit_zip(self, parent, reader: ArchiveReader, title: str, **kw) -> bool:
        if reader.fmt != "zip":
            message(parent, "info", tr("ZIP만 수정할 수 있어요", "Only ZIP can be edited"),
                    tr("이 형식은 읽기 전용이에요. '형식 변환'으로 ZIP으로 바꾼 뒤 수정하세요.", "This format is read-only. Convert to ZIP first."))
            return False
        if not self.ensure_password(parent, reader):
            return False
        path, pw = reader.path, reader.password
        reader.close()
        out = run_job(parent, title, path.name,
                      lambda cb, cancel: edit_zip(path, password=pw, progress=cb, cancel=cancel, **kw))
        if out.status == "failed":
            self.show_error(parent, out.error)
        return out.ok

    # ---- convert ----------------------------------------------------------------------------------------
    def convert(self, parent, reader: ArchiveReader) -> Optional[CompressResult]:
        if not self.ensure_password(parent, reader):
            return None
        tmp = Path(tempfile.mkdtemp(prefix="warpzip-conv-"))
        try:
            opts = ExtractOptions(folder_mode="never", propagate_motw=False)
            out = run_job(parent, tr("변환 준비 중", "Preparing"), reader.path.name,
                          lambda cb, cancel: ar.extract(reader, tmp, None, opts, cb, cancel))
            if not out.ok:
                if out.status == "failed":
                    self.show_error(parent, out.error)
                return None
            tops = sorted(tmp.iterdir())
            return self.compress_dialog(parent, tops, reader.path.parent, archive_stem(reader.path.name))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- open a single file from the archive ------------------------------------------------------------
    def open_member(self, parent, reader: ArchiveReader, entry: Entry) -> None:
        if not self.ensure_password(parent, reader):
            return
        ext = entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
        if ext in EXEC_EXT:
            if not confirm(parent, tr("실행 파일이에요", "Executable file"),
                           tr("압축 파일 안의 실행 파일을 바로 열면 위험할 수 있어요. 계속할까요?", "Opening executables straight from an archive can be risky. Continue?"),
                           tr("열기", "Open"), danger=True):
                return
        tmp = Path(tempfile.mkdtemp(prefix="warpzip-open-"))
        self._temp_dirs.append(tmp)
        opts = ExtractOptions(folder_mode="never", overwrite="overwrite", strip_prefix=entry.parent)
        out = run_job(parent, tr("파일 여는 중", "Opening file"), entry.name,
                      lambda cb, cancel: ar.extract(reader, tmp, [entry], opts, cb, cancel))
        if not out.ok:
            if out.status == "failed":
                self.show_error(parent, out.error)
            return
        target = tmp / entry.name
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def cleanup(self) -> None:
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    # ---- shell quick actions -----------------------------------------------------------------------------------
    def quick_extract(self, parent, archives: Sequence[Path], mode: str) -> None:
        """mode: here | folder | ask"""
        for a in archives:
            reader = self.open_reader(parent, Path(a))
            if reader is None:
                continue
            try:
                if mode == "ask":
                    self.extract(parent, reader)
                else:
                    opts = ExtractOptions(folder_mode="never" if mode == "here" else "always",
                                          overwrite=self.s.get("extract/overwrite"),
                                          propagate_motw=self.s.get("extract/motw"))
                    if mode == "here":
                        opts.folder_mode = "smart"
                    self.extract(parent, reader, dest=Path(a).parent, opts=opts, ask=False)
            finally:
                reader.close()

    def quick_compress(self, parent, sources: Sequence[Path], fmt: str) -> Optional[CompressResult]:
        sources = [Path(s) for s in sources]
        base = sources[0].stem if len(sources) == 1 and sources[0].is_file() else (
            sources[0].name if len(sources) == 1 else sources[0].parent.name or "archive")
        dest = sources[0].parent / (base + FORMATS[fmt].ext)
        if dest.exists():
            from ..core.security import unique_path
            dest = unique_path(dest)
        opts = CompressOptions(fmt=fmt, level=self.s.get("compress/level"),
                               exclude=[x for x in self.s.get("compress/exclude").split(";") if x])
        return self.run_compress(parent, sources, dest, opts)

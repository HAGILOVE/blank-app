"""Engine tests: round-trips, security, encodings, volumes, editing."""
import io
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest

from warpzip.core import archive as ar
from warpzip.core.archive import analyze, extract, open_archive
from warpzip.core.archive import verify_archive as check_archive
from warpzip.core.compress import CompressOptions, collect_sources, compress
from warpzip.core.edit import edit_zip
from warpzip.core.errors import (
    Cancelled, CorruptArchive, DiskSpaceError, PasswordRequired, UnsupportedFormat, WrongPassword,
)
from warpzip.core.formats import FORMATS, archive_stem, sniff_path
from warpzip.core.hashing import hash_file
from warpzip.core.progress import CancelToken
from warpzip.core.security import normalize_member_name
from warpzip.core.sink import ExtractOptions
from warpzip.core.errors import UnsafePath

WRITABLE = [k for k, f in FORMATS.items() if f.can_write]


def tree(root: Path):
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*"))


def assert_same(src: Path, dst: Path):
    for p in src.rglob("*"):
        q = dst / p.relative_to(src)
        assert q.exists(), q
        if p.is_file():
            assert q.read_bytes() == p.read_bytes()


@pytest.mark.parametrize("fmt", WRITABLE)
def test_roundtrip(fmt, sample, tmp_path):
    out = tmp_path / ("out" + FORMATS[fmt].ext)
    res = compress([sample], out, CompressOptions(fmt=fmt))
    assert out.exists() and res.files == 5 and res.dirs >= 3
    assert not list(tmp_path.glob("*.warp-part"))
    assert sniff_path(out) == fmt
    with open_archive(out) as rd:
        names = {e.path for e in rd.entries}
        assert "data/sub/deep/c.txt" in names and "data/emptydir" in names
        assert check_archive(rd) == []
        dest = tmp_path / "x"
        r = extract(rd, dest, opts=ExtractOptions(folder_mode="never"))
        assert r.ok and r.files == 5
    assert_same(sample, dest / "data")


@pytest.mark.parametrize("fmt", ["zip", "7z"])
def test_password_flow(fmt, sample, tmp_path):
    out = tmp_path / ("p" + FORMATS[fmt].ext)
    compress([sample], out, CompressOptions(fmt=fmt, password="s3cret!한글", encrypt_names=(fmt == "7z")))
    with pytest.raises(PasswordRequired):
        with open_archive(out) as rd:
            rd.verify_password()
            extract(rd, tmp_path / "n")
    try:
        with open_archive(out, password="wrong") as rd:
            rd.verify_password()
        raise AssertionError("wrong password accepted")
    except WrongPassword:
        pass
    with open_archive(out, password="s3cret!한글") as rd:
        rd.verify_password()
        assert extract(rd, tmp_path / "ok", opts=ExtractOptions(folder_mode="never")).ok
    assert_same(sample, tmp_path / "ok" / "data")


def test_zip_aes_is_really_encrypted(sample, tmp_path):
    out = tmp_path / "e.zip"
    compress([sample], out, CompressOptions(fmt="zip", password="pw"))
    raw = out.read_bytes()
    assert b"hello" not in raw and b"deep file" not in raw
    with zipfile.ZipFile(out) as z:  # stdlib sees it as encrypted (AES method 99)
        assert any(i.flag_bits & 1 for i in z.infolist() if not i.is_dir())


def test_smart_store_for_jpg(sample, tmp_path):
    out = tmp_path / "s.zip"
    compress([sample], out, CompressOptions(fmt="zip"))
    with zipfile.ZipFile(out) as z:
        assert z.getinfo("data/pic.jpg").compress_type == zipfile.ZIP_STORED
        assert z.getinfo("data/a.txt").compress_type == zipfile.ZIP_DEFLATED


# ---------------------------------------------------------------- security
def _evil_zip(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("../evil.txt", "x")
        z.writestr("..\\evil2.txt", "x")
        z.writestr("/abs/evil3.txt", "x")
        z.writestr("C:\\win\\evil4.txt", "x")
        z.writestr("ok/fine.txt", "fine")


def test_zip_slip_blocked(tmp_path):
    z = tmp_path / "evil.zip"
    _evil_zip(z)
    dest = tmp_path / "box" / "inner"
    with open_archive(z) as rd:
        res = extract(rd, dest, opts=ExtractOptions(folder_mode="never"))
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "box" / "evil.txt").exists()
    assert not (tmp_path / "box" / "evil2.txt").exists()
    assert len(res.unsafe) == 2            # the two '..' names are rejected
    assert (dest / "ok" / "fine.txt").read_text() == "fine"
    # absolute / drive paths are neutralised and stay inside dest
    inside = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert inside <= {"ok/fine.txt", "abs/evil3.txt", "win/evil4.txt"}


def test_tar_traversal_and_links(tmp_path):
    t = tmp_path / "evil.tar"
    with tarfile.open(t, "w") as tf:
        ti = tarfile.TarInfo("../../escape.txt")
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
        ln = tarfile.TarInfo("link")
        ln.type = tarfile.SYMTYPE
        ln.linkname = "/etc/passwd"
        tf.addfile(ln)
        ti = tarfile.TarInfo("good.txt")
        ti.size = 2
        tf.addfile(ti, io.BytesIO(b"ok"))
    dest = tmp_path / "d" / "e"
    with open_archive(t) as rd:
        res = extract(rd, dest, opts=ExtractOptions(folder_mode="never"))
    assert not (tmp_path / "escape.txt").exists()
    assert not (dest / "link").exists()
    assert (dest / "good.txt").read_text() == "ok"
    assert res.unsafe and "link" in res.skipped


@pytest.mark.skipif(os.name == "nt", reason="symlink privilege")
def test_symlink_dir_escape(tmp_path):
    dest = tmp_path / "dest"
    outside = tmp_path / "outside"
    outside.mkdir()
    dest.mkdir()
    (dest / "lnk").symlink_to(outside)
    z = tmp_path / "s.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("lnk/pwn.txt", "x")
    with open_archive(z) as rd:
        res = extract(rd, dest, opts=ExtractOptions(folder_mode="never"))
    assert not (outside / "pwn.txt").exists()
    assert res.unsafe


def test_normalize_names():
    assert normalize_member_name("a\\b/c.txt", windows=False) == "a/b/c.txt"
    assert normalize_member_name("./x//y", windows=False) == "x/y"
    with pytest.raises(UnsafePath):
        normalize_member_name("a/../../b")
    assert normalize_member_name('a/b:c?.txt', windows=True) == "a/b_c_.txt"
    assert normalize_member_name("CON.txt", windows=True) == "_CON.txt"
    assert normalize_member_name("end. ", windows=True) == "end"


def test_bomb_analysis(tmp_path):
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a", "x")
    with open_archive(z) as rd:
        assert not analyze(rd).suspicious
        rd.entries[0].size = 10 * 1024 ** 3
        rd.packed_size = 1000
        assert analyze(rd).suspicious


# ---------------------------------------------------------------- encodings
def _legacy_zip(path: Path, names, codec):
    placeholders = {}
    with zipfile.ZipFile(path, "w") as z:
        for i, n in enumerate(names):
            raw = n.encode(codec)
            ph = f"@{i:0{len(raw) - 1}d}".encode()  # same byte length ASCII
            placeholders[ph] = raw
            z.writestr(ph.decode(), f"content {i}")
    data = path.read_bytes()
    for ph, raw in placeholders.items():
        data = data.replace(ph, raw)
    path.write_bytes(data)


@pytest.mark.parametrize("codec,names", [
    ("cp949", ["한글 문서/보고서_최종.txt", "사진/여행 사진.jpg"]),
    ("cp932", ["日本語/ファイル名.txt", "写真/旅行.jpg"]),
    ("gbk", ["中文目录/测试文件.txt"]),
])
def test_legacy_zip_names(tmp_path, codec, names):
    z = tmp_path / "legacy.zip"
    _legacy_zip(z, names, codec)
    with open_archive(z) as rd:
        assert {e.path for e in rd.entries if not e.is_dir} == set(names)
        assert rd.detected_encoding == codec
    # explicit override works as well
    with open_archive(z, encoding=codec) as rd:
        assert {e.path for e in rd.entries} == set(names)
    # extraction writes the proper names
    with open_archive(z) as rd:
        extract(rd, tmp_path / "o", opts=ExtractOptions(folder_mode="never"))
    assert (tmp_path / "o" / names[0]).read_text().startswith("content")


def test_utf8_zip_not_mangled(tmp_path):
    z = tmp_path / "u.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("한글/파일.txt", "x")
    with open_archive(z) as rd:
        assert rd.entries[-1].path == "한글/파일.txt"


# -------------------------------------------------------------- policies
def test_overwrite_policies(sample, tmp_path):
    z = tmp_path / "o.zip"
    compress([sample], z, CompressOptions(fmt="zip"))
    dest = tmp_path / "d"
    with open_archive(z) as rd:
        extract(rd, dest, opts=ExtractOptions(folder_mode="never"))
        f = dest / "data" / "a.txt"
        f.write_text("changed")
        r = extract(rd, dest, opts=ExtractOptions(folder_mode="never", overwrite="skip"))
        assert f.read_text() == "changed" and "data/a.txt" in r.skipped
        extract(rd, dest, opts=ExtractOptions(folder_mode="never", overwrite="rename"))
        assert (dest / "data" / "a (1).txt").exists() and f.read_text() == "changed"
        extract(rd, dest, opts=ExtractOptions(folder_mode="never", overwrite="overwrite"))
        assert f.read_text(encoding="utf-8").startswith("hello")
        f.write_text("newer than archive")
        os.utime(f, (4_000_000_000, 4_000_000_000))
        extract(rd, dest, opts=ExtractOptions(folder_mode="never", overwrite="newer"))
        assert f.read_text() == "newer than archive"


def test_folder_modes(sample, tmp_path):
    z = tmp_path / "pack.zip"
    compress([sample], z, CompressOptions(fmt="zip"))
    flat = tmp_path / "flat.zip"
    compress([sample / "a.txt", sample / "empty.txt"], flat, CompressOptions(fmt="zip"))
    with open_archive(z) as rd:      # single root folder -> no wrapper
        r = extract(rd, tmp_path / "s1")
        assert r.root == tmp_path / "s1"
    with open_archive(flat) as rd:   # two root items -> wrapper named after archive
        r = extract(rd, tmp_path / "s2")
        assert r.root == tmp_path / "s2" / "flat" and (r.root / "a.txt").exists()
        r = extract(rd, tmp_path / "s3", opts=ExtractOptions(folder_mode="never"))
        assert r.root == tmp_path / "s3"
        r = extract(rd, tmp_path / "s4", opts=ExtractOptions(folder_mode="always"))
        assert r.root == tmp_path / "s4" / "flat"


def test_partial_extract(sample, tmp_path):
    z = tmp_path / "p.7z"
    compress([sample], z, CompressOptions(fmt="7z"))
    for fmt_z in (z, ):
        with open_archive(fmt_z) as rd:
            pick = [e for e in rd.entries if e.path in ("data/sub/deep/c.txt", "data/sub/deep", "data/sub", "data")]
            extract(rd, tmp_path / "part", pick, ExtractOptions(folder_mode="never"))
    assert tree(tmp_path / "part") == ["data", "data/sub", "data/sub/deep", "data/sub/deep/c.txt"]


# ---------------------------------------------------------------- volumes
@pytest.mark.parametrize("fmt", ["zip", "7z", "tar.gz"])
def test_split_volumes(fmt, sample, tmp_path):
    out = tmp_path / ("big" + FORMATS[fmt].ext)
    res = compress([sample], out, CompressOptions(fmt=fmt, split_size=64 * 1024, level=0 if fmt != "tar.gz" else 1))
    assert len(res.outputs) >= 3 and not out.exists()
    assert res.outputs[0].name.endswith(".001")
    sizes = [p.stat().st_size for p in res.outputs]
    assert all(s == 64 * 1024 for s in sizes[:-1]) and sizes[-1] <= 64 * 1024
    with open_archive(res.outputs[0]) as rd:
        assert check_archive(rd) == []
        extract(rd, tmp_path / "joined", opts=ExtractOptions(folder_mode="never"))
    assert_same(sample, tmp_path / "joined" / "data")
    assert archive_stem(res.outputs[0].name) == "big"


# ----------------------------------------------------------- misc behaviours
def test_cancel_cleans_up(sample, tmp_path):
    out = tmp_path / "c.zip"
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        compress([sample], out, CompressOptions(fmt="zip"), cancel=token)
    assert not out.exists() and not list(tmp_path.glob("*.warp-part"))


def test_cancel_during_extract(sample, tmp_path):
    z = tmp_path / "c.zip"
    compress([sample], z, CompressOptions(fmt="zip", level=0))
    token = CancelToken()
    seen = []

    def cb(p):
        seen.append(p.bytes_done)
        token.cancel()

    with open_archive(z) as rd:
        with pytest.raises(Cancelled):
            extract(rd, tmp_path / "x", opts=ExtractOptions(folder_mode="never"), progress=cb, cancel=token)


def test_progress_is_monotonic_and_completes(sample, tmp_path):
    out = tmp_path / "m.7z"
    ps = []
    compress([sample], out, CompressOptions(fmt="7z"), progress=lambda p: ps.append((p.bytes_done, p.bytes_total)))
    assert ps[-1][0] == ps[-1][1] > 0
    assert all(b >= a for (a, _), (b, _) in zip(ps, ps[1:], strict=False))


def test_disk_space_guard(sample, tmp_path, monkeypatch):
    z = tmp_path / "d.zip"
    compress([sample], z, CompressOptions(fmt="zip"))
    monkeypatch.setattr(ar.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10, 9, 1))
    with open_archive(z) as rd, pytest.raises(DiskSpaceError):
        extract(rd, tmp_path / "x")


def test_exclude_patterns_and_dest_not_included(sample, tmp_path):
    (sample / "Thumbs.db").write_text("x")
    (sample / "notes.tmp").write_text("x")
    items = collect_sources([sample], ["Thumbs.db", "*.tmp"])
    names = {i.arcname for i in items}
    assert "data/Thumbs.db" not in names and "data/notes.tmp" not in names
    # archive created inside the source folder must not include itself
    out = sample / "self.zip"
    compress([sample], out, CompressOptions(fmt="zip"))
    with open_archive(out) as rd:
        assert "data/self.zip" not in {e.path for e in rd.entries}


def test_sniff_ignores_wrong_extension(sample, tmp_path):
    out = tmp_path / "real.zip"
    compress([sample], out, CompressOptions(fmt="zip"))
    liar = tmp_path / "photo.jpg"
    shutil.copy(out, liar)
    assert sniff_path(liar) == "zip"
    with open_archive(liar) as rd:
        assert rd.fmt == "zip"
    junk = tmp_path / "junk.bin"
    junk.write_bytes(os.urandom(2000))
    with pytest.raises(UnsupportedFormat):
        open_archive(junk)


def test_single_file_gz(tmp_path):
    import gzip
    p = tmp_path / "log.txt.gz"
    with gzip.open(p, "wb") as f:
        f.write(b"line\n" * 1000)
    with open_archive(p) as rd:
        assert [e.path for e in rd.entries] == ["log.txt"] and rd.entries[0].size == 5000
        extract(rd, tmp_path / "o", opts=ExtractOptions(folder_mode="never"))
    assert (tmp_path / "o" / "log.txt").read_bytes() == b"line\n" * 1000


def test_edit_zip(sample, tmp_path):
    z = tmp_path / "e.zip"
    compress([sample], z, CompressOptions(fmt="zip"))
    extra = tmp_path / "new.txt"
    extra.write_text("brand new")
    edit_zip(z, remove=["data/sub"], add=[extra], rename={"data/a.txt": "data/renamed.txt"})
    with open_archive(z) as rd:
        names = {e.path for e in rd.entries}
        assert check_archive(rd) == []
    assert "new.txt" in names and "data/renamed.txt" in names
    assert not any(n.startswith("data/sub") for n in names) and "data/a.txt" not in names


def test_edit_encrypted_zip(sample, tmp_path):
    z = tmp_path / "e.zip"
    compress([sample], z, CompressOptions(fmt="zip", password="pw"))
    edit_zip(z, remove=["data/pic.jpg"], password="pw")
    with open_archive(z, password="pw") as rd:
        assert "data/pic.jpg" not in {e.path for e in rd.entries}
        assert check_archive(rd) == []


def test_edit_repairs_legacy_names(tmp_path):
    z = tmp_path / "l.zip"
    _legacy_zip(z, ["한글/문서.txt"], "cp949")
    edit_zip(z)
    with zipfile.ZipFile(z) as zf:
        assert zf.namelist()[0] == "한글/문서.txt" and zf.infolist()[0].flag_bits & 0x800


def test_hashes(tmp_path):
    f = tmp_path / "h.bin"
    f.write_bytes(b"warpzip")
    h = hash_file(f)
    import hashlib, zlib
    assert h["SHA256"] == hashlib.sha256(b"warpzip").hexdigest()
    assert h["CRC32"] == f"{zlib.crc32(b'warpzip'):08x}"


def test_corrupt_zip_reports_problem(sample, tmp_path):
    z = tmp_path / "bad.zip"
    compress([sample], z, CompressOptions(fmt="zip", level=0))
    data = bytearray(z.read_bytes())
    i = data.index(b"deep file")
    data[i] ^= 0xFF
    z.write_bytes(data)
    with open_archive(z) as rd:
        problems = check_archive(rd)
    assert problems and "c.txt" in problems[0]


# ------------------------------------------------------- external 7-Zip engine
@pytest.mark.skipif(not ar.ExternalReader or shutil.which("7z") is None, reason="needs 7z binary")
def test_external_engine(sample, tmp_path):
    from warpzip.core.readers import ExternalReader
    z = tmp_path / "x.wim"
    import subprocess
    subprocess.run(["7z", "a", "-twim", str(z), str(sample)], check=True, capture_output=True)
    assert sniff_path(z) == "wim"
    with open_archive(z) as rd:
        assert isinstance(rd, ExternalReader)
        assert any(e.path.endswith("c.txt") for e in rd.entries)
        r = extract(rd, tmp_path / "w", opts=ExtractOptions(folder_mode="never"))
        assert r.ok
    got = list((tmp_path / "w").rglob("c.txt"))
    assert got and got[0].read_text() == "deep file"
    assert not list((tmp_path / "w").rglob(".warpzip-*"))


# --------------------------------------------- encryption really encrypts (regression)
@pytest.mark.skipif(shutil.which("7z") is None, reason="needs 7z binary")
@pytest.mark.parametrize("fmt,level,names", [("7z", 5, False), ("7z", 0, False), ("7z", 5, True), ("zip", 5, False), ("zip", 0, False)])
def test_encryption_is_real(fmt, level, names, sample, tmp_path):
    import subprocess
    out = tmp_path / ("e" + FORMATS[fmt].ext)
    compress([sample], out, CompressOptions(fmt=fmt, level=level, password="correct horse", encrypt_names=names))
    raw = out.read_bytes()
    assert b"deep file" not in raw and b"hello" not in raw
    ok = subprocess.run(["7z", "t", "-pcorrect horse", str(out)], capture_output=True, text=True)
    assert "Everything is Ok" in ok.stdout, ok.stdout
    no = subprocess.run(["7z", "t", "-pwrong", str(out)], capture_output=True, text=True)
    assert "Everything is Ok" not in no.stdout
    # our own reader must flag the archive as encrypted and reject a wrong password
    with open_archive(out, password="correct horse") as rd:
        assert rd.encrypted
        rd.verify_password()
    with pytest.raises((WrongPassword, PasswordRequired)):
        with open_archive(out, password="wrong") as rd:
            assert rd.encrypted
            rd.verify_password()
    with pytest.raises(PasswordRequired):
        with open_archive(out) as rd:
            assert rd.encrypted
            rd.verify_password()
            raise AssertionError("should not be reachable")


# ----------------------------------------------------------------- repair
def test_repair_truncated_zip(sample, tmp_path):
    from warpzip.core.repair import repair_zip
    z = tmp_path / "ok.zip"
    compress([sample], z, CompressOptions(fmt="zip", level=5))
    data = z.read_bytes()
    broken = tmp_path / "broken.zip"
    broken.write_bytes(data[: len(data) - 400])          # central directory is gone
    with pytest.raises(CorruptArchive):
        open_archive(broken)
    res = repair_zip(broken, tmp_path / "fixed.zip")
    assert res.recovered >= 3
    with open_archive(tmp_path / "fixed.zip") as rd:
        assert check_archive(rd) == []
        names = {e.path for e in rd.entries}
        assert "data/a.txt" in names
        extract(rd, tmp_path / "fx", opts=ExtractOptions(folder_mode="never"))
    assert (tmp_path / "fx" / "data" / "a.txt").read_bytes() == (sample / "a.txt").read_bytes()


def test_repair_keeps_legacy_names_and_skips_encrypted(tmp_path, sample):
    from warpzip.core.repair import repair_zip
    z = tmp_path / "l.zip"
    _legacy_zip(z, ["한글/문서.txt"], "cp949")
    b = tmp_path / "b.zip"
    b.write_bytes(z.read_bytes()[:-60])
    repair_zip(b, tmp_path / "f.zip")
    with zipfile.ZipFile(tmp_path / "f.zip") as zf:
        assert "한글/문서.txt" in zf.namelist()
    enc = tmp_path / "e.zip"
    compress([sample / "a.txt"], enc, CompressOptions(fmt="zip", password="x"))
    bad = tmp_path / "eb.zip"
    bad.write_bytes(enc.read_bytes()[:-50])
    r2 = repair_zip(bad, tmp_path / "ef.zip")
    assert r2.recovered == 0 and any("encrypted" in f for f in r2.failed)


def test_long_path_prefix_logic(monkeypatch):
    from warpzip.core import security as sec
    monkeypatch.setattr(sec, "IS_WINDOWS", True)
    monkeypatch.setattr(sec.os.path, "abspath", lambda p: p)
    assert sec.long_path(Path("C:\\short.txt")) == Path("C:\\short.txt")

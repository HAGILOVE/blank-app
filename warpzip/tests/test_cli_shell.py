import subprocess
import sys


from warpzip import cli
from warpzip.shell import windows_integration as wi


def run(*args):
    return cli.run(list(args))


def test_cli_roundtrip(sample, tmp_path, capsys):
    z = tmp_path / "c.7z"
    assert run("a", str(z), str(sample), "-p", "pw", "-q") == 0
    assert run("l", str(z), "-p", "pw") == 0
    out = capsys.readouterr().out
    assert "data/a.txt" in out and "files" in out
    assert run("t", str(z), "-p", "pw", "-q") == 0
    dest = tmp_path / "o"
    assert run("x", str(z), "-o", str(dest), "-p", "pw", "-q") == 0
    assert (dest / "data" / "a.txt").exists()
    assert run("x", str(z), "-o", str(tmp_path / "bad"), "-p", "nope", "-q") == 3


def test_cli_errors(tmp_path, capsys):
    assert run("x", str(tmp_path / "nope.zip")) == 1
    junk = tmp_path / "j.zip"
    junk.write_bytes(b"not an archive at all")
    assert run("l", str(junk)) == 1


def test_cli_split_and_format_guess(sample, tmp_path):
    z = tmp_path / "s.tar.zst"
    assert run("a", str(z), str(sample), "--split", "64k", "-q") == 0
    assert (tmp_path / "s.tar.zst.001").exists()
    assert run("x", str(tmp_path / "s.tar.zst.001"), "-o", str(tmp_path / "o"), "-q") == 0


def test_hash_command(tmp_path, capsys):
    f = tmp_path / "f"
    f.write_bytes(b"abc")
    assert run("h", str(f)) == 0
    assert "ba7816bf" in capsys.readouterr().out   # sha256("abc")


def test_module_entry_cli(sample, tmp_path):
    z = tmp_path / "m.zip"
    r = subprocess.run([sys.executable, "-m", "warpzip", "a", str(z), str(sample), "-q"],
                       capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONPATH": str(__import__("pathlib").Path(__file__).parents[1] / "src")})
    assert r.returncode == 0 and z.exists(), r.stderr


def test_context_menu_plan():
    plan = wi.context_menu_plan("ko", cmd='"C:\\Program Files\\WarpZip\\WarpZip.exe"', icon="x.ico")
    keys = {k for k, _, _ in plan}
    assert "Software\\Classes\\*\\shell\\WarpZip.Compress\\command" in keys
    assert "Software\\Classes\\Directory\\shell\\WarpZip.QuickZip\\command" in keys
    assert "Software\\Classes\\SystemFileAssociations\\.zip\\shell\\WarpZip.Here\\command" in keys
    cmds = [v for k, n, v in plan if k.endswith("\\command")]
    assert all(c.endswith('"%1"') and c.startswith('"C:\\Program Files') for c in cmds)
    assert any("압축" in v for k, n, v in plan if n == "")
    en = wi.context_menu_plan("en", cmd="x")
    assert any("Compress with WARPZIP" in v for _, _, v in en)


def test_association_plan():
    plan = wi.association_plan([".zip", ".7z"], cmd="app")
    assert ("Software\\Classes\\.zip\\OpenWithProgids", wi.PROG_ID, "") in plan
    assert ("Software\\WarpZip\\Capabilities\\FileAssociations", ".7z", wi.PROG_ID) in plan
    assert not wi.IS_WINDOWS or True
    if not wi.IS_WINDOWS:
        assert wi.install_context_menu() is False and wi.context_menu_installed() is False

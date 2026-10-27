"""GUI smoke / behaviour tests (offscreen Qt)."""
import json
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from warpzip.core.compress import CompressOptions, compress
from warpzip.core.sink import ExtractOptions
from warpzip.settings import Settings
from warpzip.ui import theme
from warpzip.ui.actions import Actions
from warpzip.ui.i18n import set_language, tr
from warpzip.ui.main_window import MainWindow


@pytest.fixture
def env(qapp, tmp_path):
    set_language("ko")
    theme.apply(qapp, "light")
    s = Settings(str(tmp_path / "s.ini"))
    s.set("ui/auto_close_progress", True)     # never block tests on result dialogs
    s.set("extract/open_folder", False)
    return s, Actions(s)


@pytest.fixture
def zip_file(sample, tmp_path):
    z = tmp_path / "프로젝트.zip"
    compress([sample], z, CompressOptions(fmt="zip"))
    return z


def test_i18n_switch():
    set_language("en")
    assert tr("열기", "Open") == "Open"
    set_language("ko")
    assert tr("열기", "Open") == "열기"


def test_welcome_then_open_browse(env, zip_file, qtbot):
    s, actions = env
    w = MainWindow(s, actions)
    qtbot.addWidget(w)
    w.show()
    assert w.stack.currentIndex() == 0 and not w.a_extract.isEnabled()
    assert w.open_path(zip_file)
    assert w.stack.currentIndex() == 1 and w.a_extract.isEnabled()
    names = {n.name for n in w.model.rows}
    assert names == {"data"}
    w.cd("data")
    assert {"sub", "emptydir", "a.txt", "empty.txt", "pic.jpg"} == {n.name for n in w.model.rows}
    w.go_up()
    assert w.model.cwd == ""
    w.go_back() if w.history else None
    w.search.setText("c.txt")
    assert [n.name for n in w.model.rows] == ["c.txt"]
    w.search.clear()
    w.close_archive()
    assert w.stack.currentIndex() == 0 and w.reader is None


def test_proxy_sorts_folders_first_both_directions(env, zip_file, qtbot):
    s, actions = env
    w = MainWindow(s, actions)
    qtbot.addWidget(w)
    w.open_path(zip_file)
    w.cd("data")
    for order in (Qt.AscendingOrder, Qt.DescendingOrder):
        w.proxy.sort(1, order)
        kinds = [w.model.node(w.proxy.mapToSource(w.proxy.index(r, 0)).row()).is_dir for r in range(w.proxy.rowCount())]
        assert kinds == sorted(kinds, reverse=True), f"folders not on top for {order}"


def test_selected_entries_and_strip_prefix_extract(env, zip_file, tmp_path, qtbot):
    s, actions = env
    w = MainWindow(s, actions)
    qtbot.addWidget(w)
    w.open_path(zip_file)
    w.cd("data/sub")
    deep = w.tree.by_path["data/sub/deep"]
    entries = w.tree.entries_for([deep])
    assert {e.path for e in entries} == {"data/sub/deep", "data/sub/deep/c.txt"}
    out = actions.extract(w, w.reader, entries, dest=tmp_path / "out", ask=False, strip_prefix="data/sub",
                          opts=ExtractOptions(folder_mode="never"))
    assert out and (tmp_path / "out" / "deep" / "c.txt").read_text() == "deep file"


def test_actions_open_reader_and_extract_smart(env, zip_file, tmp_path, qtbot):
    s, actions = env
    rd = actions.open_reader(None, zip_file)
    assert rd is not None
    actions.extract(None, rd, dest=tmp_path / "x", ask=False, opts=ExtractOptions(folder_mode="smart"))
    rd.close()
    assert (tmp_path / "x" / "data" / "a.txt").exists()


def test_password_prompt_flow(env, sample, tmp_path, monkeypatch, qtbot):
    from warpzip.ui import actions as act_mod
    s, actions = env
    z = tmp_path / "secret.7z"
    compress([sample], z, CompressOptions(fmt="7z", password="pw!", encrypt_names=True))
    answers = iter([("wrong", False), ("pw!", True)])
    monkeypatch.setattr(act_mod, "ask_password", lambda *a, **k: next(answers))
    rd = actions.open_reader(None, z)
    assert rd is not None and rd.password == "pw!"
    assert actions.pw_cache[str(z)] == "pw!"
    rd.close()


def test_cancel_password_prompt_returns_none(env, sample, tmp_path, monkeypatch, qtbot):
    from warpzip.ui import actions as act_mod
    s, actions = env
    z = tmp_path / "secret.zip"
    compress([sample], z, CompressOptions(fmt="zip", password="pw"))
    monkeypatch.setattr(act_mod, "ask_password", lambda *a, **k: None)
    rd = actions.open_reader(None, z)          # listing works without a password
    assert rd is not None and rd.encrypted
    assert actions.ensure_password(None, rd) is False
    rd.close()


def test_edit_zip_via_actions(env, zip_file, tmp_path, qtbot):
    s, actions = env
    rd = actions.open_reader(None, zip_file)
    extra = tmp_path / "plus.txt"
    extra.write_text("plus")
    assert actions.edit_zip(None, rd, "t", add=[extra], add_prefix="data", remove=["data/pic.jpg"])
    rd2 = actions.open_reader(None, zip_file)
    names = {e.path for e in rd2.entries}
    rd2.close()
    assert "data/plus.txt" in names and "data/pic.jpg" not in names


def test_compress_dialog_roundtrip_options(env, sample, qtbot):
    from warpzip.ui.compress_dialog import CompressDialog
    s, _ = env
    d = CompressDialog(None, [sample], s)
    qtbot.addWidget(d)
    d._set_format("7z")
    d._set_level(9)
    d.pw.setText("abc")
    d.pw2.setText("abc")
    d.split.setCurrentIndex(1)
    o = d.options()
    assert (o.fmt, o.level, o.password, o.split_size) == ("7z", 9, "abc", 100 * 1024 ** 2)
    assert d.destination().name == "data.7z"
    d._set_format("tar.gz")
    assert d.options().password is None and not d.sec.isEnabled()
    d._set_format("zip")
    assert d.method.isEnabled() and d.smart.isEnabled()


def test_compress_dialog_validation(env, sample, qtbot, monkeypatch):
    from warpzip.ui import compress_dialog as cd
    s, _ = env
    d = cd.CompressDialog(None, [sample], s)
    qtbot.addWidget(d)
    shown = []
    monkeypatch.setattr(cd, "message", lambda *a, **k: shown.append(a[3]) or 0)
    d.pw.setText("aaa")
    d.pw2.setText("bbb")
    d._accept()
    assert shown and d.result() != QDialog.Accepted


def test_extract_dialog_defaults(env, zip_file, qtbot):
    from warpzip.ui.extract_dialog import ExtractDialog
    s, _ = env
    d = ExtractDialog(None, zip_file, s, 5, 1000, False, 0, False, None, True)
    qtbot.addWidget(d)
    assert d.destination() == zip_file.parent
    d._set_mode("always")
    d.over.setCurrentIndex(d.over.findData("skip"))
    o = d.options()
    assert (o.folder_mode, o.overwrite) == ("always", "skip")


def test_run_job_shows_dialog_and_finishes(env, qtbot):
    from warpzip.ui.progress_dialog import run_job

    def slow(cb, cancel):
        from warpzip.core.progress import Progress
        for i in range(10):
            cancel.check()
            cb(Progress(bytes_done=i, bytes_total=10, current=f"f{i}"))
            time.sleep(0.07)
        return "done"

    out = run_job(None, "t", "sub", slow, auto_close=True)
    assert out.ok and out.result == "done"


def test_run_job_cancel(env, qtbot):
    from warpzip.ui.progress_dialog import ProgressDialog, run_job

    def forever(cb, cancel):
        while True:
            cancel.check()
            time.sleep(0.02)

    def press_cancel():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, ProgressDialog) and w.isVisible():
                w.cancel_btn.click()
                return
        QTimer.singleShot(50, press_cancel)

    QTimer.singleShot(400, press_cancel)
    out = run_job(None, "t", "sub", forever, auto_close=True)
    assert out.status == "cancelled"


def test_run_job_error_is_reported_not_raised(env, qtbot):
    from warpzip.ui.progress_dialog import run_job
    out = run_job(None, "t", "s", lambda cb, c: 1 / 0)
    assert out.status == "failed" and isinstance(out.error, ZeroDivisionError)


def test_describe_errors():
    from warpzip.core.errors import CorruptArchive, DiskSpaceError, WrongPassword
    from warpzip.ui.actions import describe_error
    assert "손상" in describe_error(CorruptArchive("x"))[0]
    assert "공간" in describe_error(DiskSpaceError("100:10"))[0]
    assert "비밀번호" in describe_error(WrongPassword())[0]


def test_drop_archive_opens_it(env, zip_file, qtbot):
    s, actions = env
    w = MainWindow(s, actions)
    qtbot.addWidget(w)
    w.handle_dropped([str(zip_file)])
    assert w.reader is not None and w.reader.path == zip_file


def test_single_instance_forwarding(qapp, qtbot, monkeypatch):
    from warpzip import app as appmod
    monkeypatch.setattr(appmod, "SERVER_NAME", "WarpZip-test-single-%d" % time.time_ns())
    si = appmod.SingleInstance()
    result = []
    # the sender blocks until the server acks, so (like the real second process) it must not share our event loop
    t = threading.Thread(target=lambda: result.append(appmod.forward_to_running(["--compress", "C:\\a b\\c.txt"])))
    with qtbot.waitSignal(si.received, timeout=8000) as sig:
        t.start()
    t.join(8)
    assert result == [True]
    assert sig.args[0] == ["--compress", "C:\\a b\\c.txt"]


def test_strength_meter():
    from warpzip.ui.widgets import strength
    assert strength("")[0] == 0 and strength("abc")[0] < strength("Abcdefgh1234!x")[0]


def test_theme_modes(qapp):
    for mode in ("light", "dark", "auto"):
        p = theme.apply(qapp, mode)
        assert p.name in ("light", "dark")
    assert Path(theme._indicators(theme.LIGHT)["check_on"]).exists()


def test_mascot_and_icons_load(qapp):
    from warpzip.ui import icons
    for mood in ("idle", "happy", "work", "sad", "sleep", "done"):
        assert not icons.mascot(mood, 64).isNull()
    assert not icons.app_icon().isNull()
    assert not icons.file_icon("x.zip").isNull() and not icons.file_icon("d", True).isNull()
    ext = json.loads(Path(icons.asset_path("ext_icons.json")).read_text(encoding="utf-8"))
    assert ext["zip"] == "f_archive" and ext["py"] == "f_code"


# ------------------------------------------------------------------ app dispatch
@pytest.fixture
def warp(qapp, tmp_path, monkeypatch):
    from warpzip import app as appmod
    monkeypatch.setattr(appmod, "Settings", lambda: Settings(str(tmp_path / "w.ini")))
    s = Settings(str(tmp_path / "w.ini"))
    s.set("ui/auto_close_progress", True)
    w = appmod.WarpApp(qapp, s)
    yield w
    if w.window:
        w.window.close()


def test_app_handle_args_opens_archive(warp, zip_file, qtbot):
    warp.handle_args([])
    assert warp.window.isVisible()
    warp.handle_args([str(zip_file)])
    assert warp.window.reader is not None and warp.window.reader.path == zip_file


def test_app_aggregates_multi_select_compress(warp, tmp_path, monkeypatch, qtbot):
    got = []
    monkeypatch.setattr(warp.actions, "compress_dialog", lambda parent, paths, *a, **k: got.append(list(paths)))
    for name in ("a.txt", "b.txt", "c.txt", "a.txt"):
        warp.handle_args(["--compress", str(tmp_path / name)])
    qtbot.waitUntil(lambda: bool(got), timeout=3000)
    assert got == [[tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"]]   # one dialog, duplicates removed


def test_app_quick_extract_here(warp, zip_file, tmp_path, qtbot):
    d = tmp_path / "ex"
    d.mkdir()
    target = d / zip_file.name
    target.write_bytes(zip_file.read_bytes())
    warp.s.set("extract/open_folder", False)
    warp.handle_args(["--extract-here", str(target)])
    qtbot.waitUntil(lambda: (d / "data" / "a.txt").exists(), timeout=5000)


def test_app_quick_zip_names_after_single_file(warp, tmp_path, qtbot):
    f = tmp_path / "report.txt"
    f.write_text("hi")
    warp.handle_args(["--quick-zip", str(f)])
    qtbot.waitUntil(lambda: (tmp_path / "report.zip").exists(), timeout=5000)
    warp.handle_args(["--quick-zip", str(f)])           # second run must not overwrite
    qtbot.waitUntil(lambda: (tmp_path / "report (1).zip").exists(), timeout=5000)


def test_rebuild_window_keeps_open_archive(warp, zip_file, qtbot):
    warp.handle_args([str(zip_file)])
    warp.window.cd("data")
    warp.s.set("theme", "dark")
    warp.rebuild_window()
    assert warp.window.reader.path == zip_file and warp.window.model.cwd == "data"

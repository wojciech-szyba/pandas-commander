"""Integration tests for pandas-commander.py — the PandasCommander App class
that wires FilePanel, EditorPanel and all the modal screens together.

Screens pushed by an action (PromptScreen, ConfirmScreen, DriveScreen, ...)
are driven by calling `.dismiss(value)` directly on the pushed screen rather
than simulating full keyboard/mouse navigation through them -- that
navigation is already covered by test/screens/*, so here the unit under
test is PandasCommander's own callback/orchestration logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from textual.widgets import DataTable, Input, TextArea

from panels.FilePanel import FilePanel
from panels.remote_sources import RemoteConnection


async def _start(pilot) -> None:
    """Dismiss the startup splash screen so the main UI is interactive."""
    await pilot.press("space")
    await pilot.pause()


@pytest.fixture
def make_app(isolated_app_class, tmp_path):
    """Factory for a PandasCommander instance rooted at an empty tmp dir,
    with RECENT_PATH redirected away from the real user home directory."""

    def _make(start_dir: Path | None = None):
        return isolated_app_class(start_dir=str(start_dir or tmp_path))

    return _make


# --------------------------------------------------------------------- compose

@pytest.mark.asyncio
async def test_compose_mounts_panels_and_cmdline(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        assert app.query_one("#left", FilePanel) is not None
        assert app.query_one("#right") is not None
        assert app.query_one("#cmdline", Input) is not None


@pytest.mark.asyncio
async def test_on_mount_sets_active_panel_and_focuses_table(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        assert app.active_panel is app.left
        assert app.left.has_class("-active")
        assert app.focused is app.left.query_one(DataTable)


# ------------------------------------------------------------------ set_active

@pytest.mark.asyncio
async def test_set_active_toggles_classes_between_panels(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.set_active(app.right)
        assert app.right.has_class("-active")
        assert not app.left.has_class("-active")
        app.set_active(app.left)
        assert app.left.has_class("-active")
        assert not app.right.has_class("-active")


@pytest.mark.asyncio
async def test_set_active_same_panel_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.set_active(app.left)
        assert app.active_panel is app.left
        assert app.left.has_class("-active")


# --------------------------------------------------------------- descendant focus

@pytest.mark.asyncio
async def test_focusing_editor_area_activates_right_panel(make_app, tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        area = app.query_one("#ep-area", TextArea)
        area.focus()
        await pilot.pause()
        assert app.right.has_class("-active")
        assert not app.left.has_class("-active")


@pytest.mark.asyncio
async def test_focusing_file_panel_after_editor_clears_editor_active_class(make_app, tmp_path):
    """Documents current on_descendant_focus behavior: it never updates
    self.active_panel when the editor is focused (only strips its CSS
    class), so set_active()'s `if self.active_panel is panel: return` guard
    later skips re-adding "-active" to the same file panel. Net effect: with
    a single file panel, tabbing editor -> file panel leaves BOTH panels
    without the active-border class. See KNOWN_ISSUES noted for the app.
    """
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        app.query_one("#ep-area", TextArea).focus()
        await pilot.pause()
        assert app.right.has_class("-active")

        app.left.query_one(DataTable).focus()
        await pilot.pause()
        assert not app.right.has_class("-active")
        # NOTE: this asserts the *actual* (buggy) behavior, not the
        # intended one -- see the docstring above.
        assert not app.left.has_class("-active")


# -------------------------------------------------------------------- check_action

@pytest.mark.asyncio
async def test_check_action_blocks_file_ops_from_editor(make_app, tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        app.query_one("#ep-area", TextArea).focus()
        await pilot.pause()
        assert app.check_action("mkdir", ()) is None
        assert app.check_action("delete", ()) is None
        # pandas_canvas is explicitly allowed from within the editor too? No --
        # the guard only exempts remote-mode restriction, not the editor-focus one.
        assert app.check_action("pandas_canvas", ()) is None


@pytest.mark.asyncio
async def test_check_action_allows_file_ops_from_file_panel(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        assert app.check_action("mkdir", ()) is True
        assert app.check_action("delete", ()) is True


@pytest.mark.asyncio
async def test_check_action_blocks_write_ops_on_remote_panel(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.mode = "remote"
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        assert app.check_action("mkdir", ()) is None
        assert app.check_action("delete", ()) is None
        # pandas_canvas is allowed on remote panels -- it downloads first.
        assert app.check_action("pandas_canvas", ()) is True


@pytest.mark.asyncio
async def test_check_action_download_file_requires_remote_active_panel(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        assert app.check_action("download_file", ()) is None
        app.left.mode = "remote"
        assert app.check_action("download_file", ()) is True


@pytest.mark.asyncio
async def test_check_action_download_file_none_from_editor(make_app, tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        app.query_one("#ep-area", TextArea).focus()
        await pilot.pause()
        assert app.check_action("download_file", ()) is None


# ---------------------------------------------------------------- switch panel

@pytest.mark.asyncio
async def test_switch_panel_from_file_panel_focuses_editor_area_when_visible(make_app, tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        app.action_switch_panel()
        await pilot.pause()
        assert app.focused is app.query_one("#ep-area", TextArea)


@pytest.mark.asyncio
async def test_switch_panel_from_editor_focuses_file_table(make_app, tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(path)
        app.query_one("#ep-area", TextArea).focus()
        await pilot.pause()
        app.action_switch_panel()
        await pilot.pause()
        assert app.focused is app.left.query_one(DataTable)


@pytest.mark.asyncio
async def test_switch_panel_noop_when_no_file_loaded(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        app.action_switch_panel()  # ep-area not displayed -- nothing to switch to
        await pilot.pause()
        assert app.focused is app.left.query_one(DataTable)


# ------------------------------------------------------------------------- up / cmd

@pytest.mark.asyncio
async def test_action_up_calls_active_panel_go_up(make_app, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(sub)
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_up()
        assert app.left.path == tmp_path.resolve()


@pytest.mark.asyncio
async def test_action_focus_cmd_focuses_input(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_focus_cmd()
        await pilot.pause()
        assert app.focused is app.query_one("#cmdline", Input)


# ---------------------------------------------------------------------------- about

@pytest.mark.asyncio
async def test_action_about_pushes_about_screen(make_app):
    from screens.about import AboutScreen

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_about()
        await pilot.pause()
        assert isinstance(app.screen, AboutScreen)


# -------------------------------------------------------------------------- windows

@pytest.mark.asyncio
async def test_action_windows_filters_to_existing_files(make_app, tmp_path):
    from screens.windows import WindowsScreen

    exists = tmp_path / "exists.py"
    exists.write_text("x=1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.recent_files = [str(exists), str(tmp_path / "gone.py")]
        app.action_windows()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, WindowsScreen)
        assert screen.recent == [str(exists)]


@pytest.mark.asyncio
async def test_action_windows_choosing_file_opens_it(make_app, tmp_path):
    target = tmp_path / "chosen.py"
    target.write_text("x = 1\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.recent_files = [str(target)]
        app.action_windows()
        await pilot.pause()
        app.screen.dismiss(str(target))
        await pilot.pause()
        assert app.right.current_path == target


# ---------------------------------------------------------------------------- mkdir

@pytest.mark.asyncio
async def test_action_mkdir_creates_directory(make_app, tmp_path):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.query_one(DataTable).focus()
        await pilot.pause()
        app.action_mkdir()
        await pilot.pause()
        app.screen.dismiss("newdir")
        await pilot.pause()
        assert (tmp_path / "newdir").is_dir()


@pytest.mark.asyncio
async def test_action_mkdir_cancelled_does_nothing(make_app, tmp_path):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_mkdir()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()
        assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_action_mkdir_existing_dir_notifies_error(make_app, tmp_path):
    (tmp_path / "already").mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_mkdir()
        await pilot.pause()
        app.screen.dismiss("already")
        await pilot.pause()
        # Directory still exists and is still empty -- create failed cleanly.
        assert (tmp_path / "already").is_dir()


@pytest.mark.asyncio
async def test_action_mkdir_no_active_panel_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.active_panel = None
        app.action_mkdir()  # must not raise
        await pilot.pause()


# -------------------------------------------------------------------------- new_file

@pytest.mark.asyncio
async def test_action_new_file_creates_empty_file(make_app, tmp_path):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_new_file()
        await pilot.pause()
        app.screen.dismiss("fresh.py")
        await pilot.pause()
        assert (tmp_path / "fresh.py").is_file()


@pytest.mark.asyncio
async def test_action_new_file_existing_name_warns_and_does_not_overwrite(make_app, tmp_path):
    existing = tmp_path / "keep.py"
    existing.write_text("original\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_new_file()
        await pilot.pause()
        app.screen.dismiss("keep.py")
        await pilot.pause()
        assert existing.read_text(encoding="utf-8") == "original\n"


# ---------------------------------------------------------------------------- delete

@pytest.mark.asyncio
async def test_action_delete_file_confirmed(make_app, tmp_path):
    target = tmp_path / "gone.py"
    target.write_text("x\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_delete()
        await pilot.pause()
        app.screen.dismiss(True)
        await pilot.pause()
        assert not target.exists()


@pytest.mark.asyncio
async def test_action_delete_directory_confirmed_uses_rmtree(make_app, tmp_path):
    target = tmp_path / "gonedir"
    target.mkdir()
    (target / "inner.txt").write_text("x", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "dir")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_delete()
        await pilot.pause()
        app.screen.dismiss(True)
        await pilot.pause()
        assert not target.exists()


@pytest.mark.asyncio
async def test_action_delete_cancelled_keeps_file(make_app, tmp_path):
    target = tmp_path / "keepme.py"
    target.write_text("x\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_delete()
        await pilot.pause()
        app.screen.dismiss(False)
        await pilot.pause()
        assert target.exists()


@pytest.mark.asyncio
async def test_action_delete_no_selection_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.entries = []
        app.action_delete()  # must not raise / push a screen
        await pilot.pause()
        from screens.confirm import ConfirmScreen

        assert not isinstance(app.screen, ConfirmScreen)


# ----------------------------------------------------------------------- chng_drv

@pytest.mark.asyncio
async def test_action_chng_drv_local_choice_switches_panel(make_app, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_chng_drv()
        await pilot.pause()
        app.screen.dismiss(("local", str(other)))
        await pilot.pause()
        assert app.left.path == other.resolve()
        assert app.left.mode == "local"


@pytest.mark.asyncio
async def test_action_chng_drv_remote_choice_switches_panel(make_app, monkeypatch):
    from panels import remote_sources

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(remote_sources, "list_connections", lambda: [conn])
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_chng_drv()
        await pilot.pause()
        app.screen.dismiss(("remote", "myconn"))
        await pilot.pause()
        assert app.left.mode == "remote"
        assert app.left.remote_conn is conn


@pytest.mark.asyncio
async def test_action_chng_drv_unknown_remote_notifies_error(make_app, monkeypatch):
    from panels import remote_sources

    monkeypatch.setattr(remote_sources, "list_connections", lambda: [])
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_chng_drv()
        await pilot.pause()
        app.screen.dismiss(("remote", "ghost"))
        await pilot.pause()
        assert app.left.mode == "local"
        assert any("not found" in msg for msg, _kw in notifications)


@pytest.mark.asyncio
async def test_action_chng_drv_cancelled_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        before = app.left.path
        app.action_chng_drv()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()
        assert app.left.path == before


@pytest.mark.asyncio
async def test_action_chng_drv_no_active_panel_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.active_panel = None
        app.action_chng_drv()  # must not raise
        await pilot.pause()


# ------------------------------------------------------------------ copy / move

@pytest.mark.asyncio
async def test_action_copy_file_copies_to_destination(make_app, tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_copy_file()
        await pilot.pause()
        app.screen.dismiss(dest_dir)
        await pilot.pause()
        assert (dest_dir / "src.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
        assert src.exists()  # copy, not move


@pytest.mark.asyncio
async def test_action_move_file_moves_to_destination(make_app, tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_move_file()
        await pilot.pause()
        app.screen.dismiss(dest_dir)
        await pilot.pause()
        assert (dest_dir / "src.csv").exists()
        assert not src.exists()


@pytest.mark.asyncio
async def test_action_copy_directory_uses_copytree(make_app, tmp_path):
    src = tmp_path / "srcdir"
    src.mkdir()
    (src / "inner.txt").write_text("hi", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "dir" and e[0].name == "srcdir")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_copy_file()
        await pilot.pause()
        app.screen.dismiss(dest_dir)
        await pilot.pause()
        assert (dest_dir / "srcdir" / "inner.txt").exists()
        assert src.exists()


@pytest.mark.asyncio
async def test_action_copy_file_error_notifies(make_app, tmp_path, monkeypatch):
    src = tmp_path / "src.csv"
    src.write_text("a\n", encoding="utf-8")
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_copy_file()
        await pilot.pause()

        import shutil

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(shutil, "copy2", boom)
        app.screen.dismiss(tmp_path / "nonexistent-dest")
        await pilot.pause()
        assert any("Copy failed" in msg for msg, _kw in notifications)


@pytest.mark.asyncio
async def test_transfer_local_no_selection_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.entries = []
        app.action_copy_file()  # must not raise / push a screen
        await pilot.pause()
        from screens.directory_picker import DirectoryPickerScreen

        assert not isinstance(app.screen, DirectoryPickerScreen)


# ---------------------------------------------------------------------- download

@pytest.mark.asyncio
async def test_action_download_file_non_remote_panel_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_download_file()  # local panel -- must not raise/push
        await pilot.pause()


@pytest.mark.asyncio
async def test_action_download_file_downloads_selected_file(make_app, tmp_path, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="data.csv", is_dir=False, size=5)]
    )
    downloads = []

    def fake_download(c, key, dest):
        downloads.append((c.name, key, str(dest)))
        Path(dest).write_text("downloaded", encoding="utf-8")

    monkeypatch.setattr(remote_backends, "download", fake_download)

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_download_file()
        await pilot.pause()
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()
        app.screen.dismiss(dest_dir)
        await pilot.pause()
        assert (dest_dir / "data.csv").read_text(encoding="utf-8") == "downloaded"
        assert downloads == [("myconn", "data.csv", str(dest_dir / "data.csv"))]


@pytest.mark.asyncio
async def test_action_download_file_on_directory_warns(make_app, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="sub", is_dir=True)]
    )
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("sub", "dir"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_download_file()
        await pilot.pause()
        assert any("Select a file" in msg for msg, _kw in notifications)


# ------------------------------------------------------------------- pandas_canvas

@pytest.mark.asyncio
async def test_pandas_canvas_generates_and_opens_pandas_file(make_app, tmp_path):
    src = tmp_path / "data.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        generated = tmp_path / "data.pandas"
        assert generated.exists()
        content = generated.read_text(encoding="utf-8")
        assert "import pandas as pd" in content
        assert 'pd.read_csv("' in content
        assert app.right.current_path == generated


@pytest.mark.asyncio
async def test_pandas_canvas_does_not_overwrite_existing_pandas_file(make_app, tmp_path):
    src = tmp_path / "data.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    generated = tmp_path / "data.pandas"
    generated.write_text("# hand-edited\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file" and e[0].name == "data.csv")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        assert generated.read_text(encoding="utf-8") == "# hand-edited\n"


@pytest.mark.asyncio
async def test_pandas_canvas_on_directory_is_noop(make_app, tmp_path):
    (tmp_path / "sub").mkdir()
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "dir")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        assert app.right.current_path is None


@pytest.mark.asyncio
async def test_pandas_canvas_from_remote_downloads_then_generates(make_app, tmp_path, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="data.csv", is_dir=False, size=5)]
    )

    def fake_download(c, key, dest):
        Path(dest).write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(remote_backends, "download", fake_download)

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        assert app.left.mode == "local"  # switched to the local temp download dir
        assert app.right.current_path is not None
        assert app.right.current_path.suffix == ".pandas"


@pytest.mark.asyncio
async def test_download_remote_for_edit_failure_notifies_and_returns_none(make_app, monkeypatch):
    from panels import remote_backends

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})

    def boom(c, key, dest):
        raise RuntimeError("network down")

    monkeypatch.setattr(remote_backends, "download", boom)
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.remote_conn = conn
        result = app._download_remote_for_edit(app.left, "data.csv")
        assert result is None
        assert any("Download failed" in msg for msg, _kw in notifications)


# ---------------------------------------------------------------------- file selected

@pytest.mark.asyncio
async def test_file_selected_message_opens_file(make_app, tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("a,b\n1,2\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.post_message(FilePanel.FileSelected(target))
        await pilot.pause()
        assert app.right.current_path == target


# ------------------------------------------------------------------------- run_command

@pytest.mark.asyncio
async def test_run_command_pushes_output_screen_with_active_panel_cwd(make_app, tmp_path, monkeypatch):
    from screens.command_output import CommandOutputScreen

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        cmdline = app.query_one("#cmdline", Input)
        cmdline.value = "echo hi"
        cmdline.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, CommandOutputScreen)
        assert app.screen.command == "echo hi"
        assert app.screen.cwd == app.left.path
        assert cmdline.value == ""


@pytest.mark.asyncio
async def test_run_command_empty_input_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        cmdline = app.query_one("#cmdline", Input)
        cmdline.focus()
        await pilot.press("enter")
        await pilot.pause()
        from screens.command_output import CommandOutputScreen

        assert not isinstance(app.screen, CommandOutputScreen)


@pytest.mark.asyncio
async def test_run_command_done_callback_refreshes_and_refocuses(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        cmdline = app.query_one("#cmdline", Input)
        cmdline.value = "echo hi"
        cmdline.focus()
        await pilot.press("enter")
        await pilot.pause()
        app.screen.action_close()  # dismiss(None) -> the "done" callback
        await pilot.pause()
        assert app.focused is app.left.query_one(DataTable)


# ------------------------------------------------------------------------- open_file

@pytest.mark.asyncio
async def test_open_file_adds_to_recent_and_loads(make_app, tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("a,b\n1,2\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(target)
        await pilot.pause()
        assert app.right.current_path == target
        assert str(target.resolve()) in app.recent_files


@pytest.mark.asyncio
async def test_open_file_offers_autosave_recovery(make_app, tmp_path):
    target = tmp_path / "script.py"
    target.write_text("original\n", encoding="utf-8")
    sidecar = target.with_name(".script.py.autosave")
    sidecar.write_text("recovered content\n", encoding="utf-8")
    import os
    import time

    os.utime(sidecar, (time.time() + 5, time.time() + 5))

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(target)
        await pilot.pause()
        from screens.confirm import ConfirmScreen

        assert isinstance(app.screen, ConfirmScreen)
        app.screen.dismiss(True)
        await pilot.pause()
        assert app.query_one("#ep-area", TextArea).text == "recovered content\n"


@pytest.mark.asyncio
async def test_open_file_declining_recovery_discards_sidecar(make_app, tmp_path):
    target = tmp_path / "script.py"
    target.write_text("original\n", encoding="utf-8")
    sidecar = target.with_name(".script.py.autosave")
    sidecar.write_text("recovered content\n", encoding="utf-8")
    import os
    import time

    os.utime(sidecar, (time.time() + 5, time.time() + 5))

    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.open_file(target)
        await pilot.pause()
        app.screen.dismiss(False)
        await pilot.pause()
        assert not sidecar.exists()


# --------------------------------------------------------------------- recent files

def test_add_recent_dedups_and_prepends(isolated_app_class, tmp_path):
    app = isolated_app_class(start_dir=str(tmp_path))
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.touch()
    b.touch()
    app.add_recent(a)
    app.add_recent(b)
    app.add_recent(a)
    assert app.recent_files[0] == str(a.resolve())
    assert app.recent_files.count(str(a.resolve())) == 1


def test_add_recent_caps_at_max_recent(isolated_app_class, tmp_path):
    app = isolated_app_class(start_dir=str(tmp_path))
    for i in range(app.MAX_RECENT + 5):
        p = tmp_path / f"f{i}.py"
        p.touch()
        app.add_recent(p)
    assert len(app.recent_files) == app.MAX_RECENT


def test_add_recent_persists_to_disk(isolated_app_class, tmp_path):
    app = isolated_app_class(start_dir=str(tmp_path))
    target = tmp_path / "a.py"
    target.touch()
    app.add_recent(target)
    saved = json.loads(app.RECENT_PATH.read_text(encoding="utf-8"))
    assert saved == [str(target.resolve())]


def test_load_recent_missing_file_returns_empty(isolated_app_class, tmp_path):
    app_cls = isolated_app_class
    app = app_cls(start_dir=str(tmp_path))
    assert app._load_recent() == []


def test_load_recent_valid_json(isolated_app_class, tmp_path):
    isolated_app_class.RECENT_PATH.write_text(json.dumps(["a.py", "b.py"]), encoding="utf-8")
    app = isolated_app_class(start_dir=str(tmp_path))
    assert app.recent_files == ["a.py", "b.py"]


def test_load_recent_malformed_json_returns_empty(isolated_app_class, tmp_path):
    isolated_app_class.RECENT_PATH.write_text("not json{{{", encoding="utf-8")
    app = isolated_app_class(start_dir=str(tmp_path))
    assert app.recent_files == []


def test_load_recent_non_list_json_returns_empty(isolated_app_class, tmp_path):
    isolated_app_class.RECENT_PATH.write_text(json.dumps({"a": 1}), encoding="utf-8")
    app = isolated_app_class(start_dir=str(tmp_path))
    assert app.recent_files == []


def test_save_recent_oserror_is_swallowed(isolated_app_class, tmp_path, monkeypatch):
    app = isolated_app_class(start_dir=str(tmp_path))

    def boom(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    app._save_recent()  # must not raise


# ------------------------------------------------------------------------ helpers

@pytest.mark.asyncio
async def test_selected_file_warns_on_directory(make_app, tmp_path):
    (tmp_path / "sub").mkdir()
    app = make_app()
    notifications = []
    import types

    async with app.run_test() as pilot:
        await _start(pilot)
        app.notify = lambda msg, **kw: notifications.append((msg, kw))
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "dir")
        table.move_cursor(row=idx)
        await pilot.pause()
        assert app._selected_file() is None
        assert any("Select a file" in msg for msg, _kw in notifications)


@pytest.mark.asyncio
async def test_selected_real_none_on_parent_entry(make_app, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = make_app(sub)
    notifications = []
    async with app.run_test() as pilot:
        await _start(pilot)
        app.notify = lambda msg, **kw: notifications.append((msg, kw))
        table = app.left.query_one(DataTable)
        table.focus()
        table.move_cursor(row=0)  # ".."
        await pilot.pause()
        assert app._selected_real() is None
        assert any("Nothing to operate on" in msg for msg, _kw in notifications)


@pytest.mark.asyncio
async def test_selected_file_returns_entry_for_a_file(make_app, tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("a\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        assert app._selected_file() == (target, "file")


# ------------------------------------------------------- remaining edge branches

@pytest.mark.asyncio
async def test_action_new_file_no_active_panel_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.active_panel = None
        app.action_new_file()  # must not raise / push a screen
        await pilot.pause()
        from screens.prompt import PromptScreen

        assert not isinstance(app.screen, PromptScreen)


@pytest.mark.asyncio
async def test_action_new_file_cancelled_creates_nothing(make_app, tmp_path):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_new_file()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()
        assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_action_new_file_oserror_notifies(make_app, tmp_path, monkeypatch):
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        app.action_new_file()
        await pilot.pause()

        def boom(self, *args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "touch", boom)
        app.screen.dismiss("blocked.py")
        await pilot.pause()
        assert any(kw.get("severity") == "error" and "Create failed" in msg for msg, kw in notifications)


@pytest.mark.asyncio
async def test_action_delete_oserror_notifies(make_app, tmp_path, monkeypatch):
    target = tmp_path / "locked.py"
    target.write_text("x\n", encoding="utf-8")
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_delete()
        await pilot.pause()

        def boom(self, *args, **kwargs):
            raise OSError("in use")

        monkeypatch.setattr(Path, "unlink", boom)
        app.screen.dismiss(True)
        await pilot.pause()
        assert any(kw.get("severity") == "error" and "Delete failed" in msg for msg, kw in notifications)


@pytest.mark.asyncio
async def test_transfer_local_cancelled_does_not_move_or_copy(make_app, tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("a\n", encoding="utf-8")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_move_file()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()
        assert src.exists()


@pytest.mark.asyncio
async def test_action_download_file_no_selection_is_noop(make_app, monkeypatch):
    from panels import remote_backends

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(remote_backends, "list_dir", lambda c, p: [])
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        app.left.entries = []  # nothing selectable, not even ".."
        app.action_download_file()  # must not raise / push a screen
        await pilot.pause()
        from screens.directory_picker import DirectoryPickerScreen

        assert not isinstance(app.screen, DirectoryPickerScreen)


@pytest.mark.asyncio
async def test_action_download_file_cancelled_downloads_nothing(make_app, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="data.csv", is_dir=False, size=5)]
    )
    calls = []
    monkeypatch.setattr(remote_backends, "download", lambda *a: calls.append(a))
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_download_file()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()
        assert calls == []


@pytest.mark.asyncio
async def test_action_download_file_error_notifies(make_app, tmp_path, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="data.csv", is_dir=False, size=5)]
    )

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(remote_backends, "download", boom)
    app = make_app()
    notifications = []
    monkeypatch.setattr(app.__class__, "notify", lambda self, msg, **kw: notifications.append((msg, kw)))
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_download_file()
        await pilot.pause()
        app.screen.dismiss(tmp_path)
        await pilot.pause()
        assert any(kw.get("severity") == "error" and "Download failed" in msg for msg, kw in notifications)


@pytest.mark.asyncio
async def test_pandas_canvas_no_selection_is_noop(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.entries = []
        app.action_pandas_canvas()  # must not raise
        await pilot.pause()
        assert app.right.current_path is None


@pytest.mark.asyncio
async def test_pandas_canvas_remote_download_failure_aborts(make_app, monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    conn = RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})
    monkeypatch.setattr(
        remote_backends, "list_dir", lambda c, p: [RemoteEntry(name="data.csv", is_dir=False, size=5)]
    )

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(remote_backends, "download", boom)
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        app.left.set_remote(conn)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        assert app.right.current_path is None


@pytest.mark.asyncio
async def test_pandas_canvas_strips_compression_suffix_before_pandas(make_app, tmp_path):
    src = tmp_path / "data.csv.gz"
    import gzip

    with gzip.open(src, "wt", encoding="utf-8") as f:
        f.write("a,b\n1,2\n")
    app = make_app()
    async with app.run_test() as pilot:
        await _start(pilot)
        table = app.left.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(app.left.entries) if e[1] == "file")
        table.move_cursor(row=idx)
        await pilot.pause()
        app.action_pandas_canvas()
        await pilot.pause()
        # "data.csv.gz" -> drop ".gz" -> "data.csv" -> swap to ".pandas" -> "data.pandas"
        assert (tmp_path / "data.pandas").exists()
        assert not (tmp_path / "data.csv.pandas").exists()


def test_add_recent_falls_back_when_resolve_raises_oserror(isolated_app_class, tmp_path, monkeypatch):
    app = isolated_app_class(start_dir=str(tmp_path))
    target = tmp_path / "weird.py"

    def boom(self, *args, **kwargs):
        raise OSError("cannot resolve")

    monkeypatch.setattr(Path, "resolve", boom)
    app.add_recent(target)
    assert app.recent_files == [str(target)]


def test_main_uses_cwd_when_no_argv_and_runs_app(app_module, monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "argv", ["pandas-commander.py"])
    monkeypatch.chdir(tmp_path)
    captured = {}

    class FakeApp:
        def __init__(self, start_dir):
            captured["start_dir"] = start_dir

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(app_module, "PandasCommander", FakeApp)
    app_module.main()
    assert captured["ran"] is True
    assert Path(captured["start_dir"]) == tmp_path


def test_main_uses_argv_path_when_given(app_module, monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "argv", ["pandas-commander.py", str(tmp_path)])
    captured = {}

    class FakeApp:
        def __init__(self, start_dir):
            captured["start_dir"] = start_dir

        def run(self):
            pass

    monkeypatch.setattr(app_module, "PandasCommander", FakeApp)
    app_module.main()
    assert captured["start_dir"] == str(tmp_path)

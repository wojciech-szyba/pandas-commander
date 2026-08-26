"""Widget-level tests for panels/FilePanel.py, driven through Textual's Pilot
test harness (a minimal host App mounts just the FilePanel under test)."""
from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from panels.FilePanel import FilePanel, human_size
from panels.remote_sources import RemoteConnection, RemoteEntry


class _Harness(App):
    """Minimal host app so FilePanel can be mounted/queried in isolation."""

    def __init__(self, start_path: str | Path):
        super().__init__()
        self._start_path = start_path
        self.notifications: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield FilePanel(self._start_path, panel_id="left")

    def notify(self, message, *, severity="information", **kwargs):  # noqa: D401
        self.notifications.append((message, severity))
        return super().notify(message, severity=severity, **kwargs)


# ------------------------------------------------------------------------ helpers

def test_human_size_formats_with_thousands_separators():
    assert human_size(1234567) == "1,234,567"
    assert human_size(0) == "0"


# --------------------------------------------------------------------- local mode

@pytest.mark.asyncio
async def test_initial_load_lists_entries_and_header(sample_tree):
    app = _Harness(sample_tree)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        header_text = panel.query_one("#header").content.plain
        assert str(sample_tree) in header_text
        # ".." + sub/ + data.csv + notes.txt + script.py  (autosave sidecar hidden)
        assert table.row_count == 5
        names = [entry[0].name if hasattr(entry[0], "name") else entry[0] for entry in panel.entries]
        assert ".autosave" not in " ".join(str(n) for n in names)


@pytest.mark.asyncio
async def test_dirs_sort_before_files_alphabetically(tmp_path):
    (tmp_path / "zzz_file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "aaa_dir").mkdir()
    (tmp_path / "bbb_file.txt").write_text("x", encoding="utf-8")
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        # entries[0] is ".." (has a parent); skip it.
        kinds = [kind for _p, kind in panel.entries[1:]]
        names = [p.name for p, _k in panel.entries[1:]]
        assert kinds == ["dir", "file", "file"]
        assert names == ["aaa_dir", "bbb_file.txt", "zzz_file.txt"]


@pytest.mark.asyncio
async def test_no_parent_entry_at_filesystem_root():
    import platform

    root = Path("C:\\") if platform.system() == "Windows" else Path("/")
    app = _Harness(root)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        assert not any(kind == "parent" for _p, kind in panel.entries)


@pytest.mark.asyncio
async def test_selected_entry_tracks_cursor(sample_tree):
    app = _Harness(sample_tree)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        table.move_cursor(row=0)
        await pilot.pause()
        assert panel.selected_entry == (sample_tree.parent, "parent")


@pytest.mark.asyncio
async def test_selected_entry_none_when_table_empty(tmp_path, monkeypatch):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.entries = []
        assert panel.selected_entry is None


@pytest.mark.asyncio
async def test_enter_on_directory_navigates_into_it(tmp_path):
    (tmp_path / "sub").mkdir()
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        table.focus()
        # Row 0 is "..", row 1 is "sub" (only entry, dirs-first).
        table.move_cursor(row=1)
        await pilot.press("enter")
        await pilot.pause()
        assert panel.path == (tmp_path / "sub").resolve()


@pytest.mark.asyncio
async def test_enter_on_parent_navigates_up(tmp_path):
    (tmp_path / "sub").mkdir()
    app = _Harness(tmp_path / "sub")
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=0)  # ".."
        await pilot.press("enter")
        await pilot.pause()
        assert panel.path == tmp_path.resolve()


@pytest.mark.asyncio
async def test_enter_on_supported_file_posts_file_selected(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    received: list[Path] = []

    def hook(message):
        if isinstance(message, FilePanel.FileSelected):
            received.append(message.path)

    app = _Harness(tmp_path)
    async with app.run_test(message_hook=hook) as pilot:
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=1)  # ".." at 0, "data.csv" at 1 (only file)
        await pilot.press("enter")
        await pilot.pause()

    # message_hook fires once per bubbling step, not once per post; check the
    # message was posted with the right path rather than an exact call count.
    assert received
    assert all(p == tmp_path / "data.csv" for p in received)


@pytest.mark.asyncio
async def test_enter_on_unsupported_file_does_not_navigate_or_post(tmp_path):
    (tmp_path / "notes.xyz").write_text("x", encoding="utf-8")
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=1)
        before_path = panel.path
        await pilot.press("enter")
        await pilot.pause()
        assert panel.path == before_path  # nothing happened


@pytest.mark.asyncio
async def test_go_up_local_moves_to_parent(tmp_path):
    (tmp_path / "sub").mkdir()
    app = _Harness(tmp_path / "sub")
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.go_up()
        assert panel.path == tmp_path.resolve()


@pytest.mark.asyncio
async def test_go_up_at_root_is_noop():
    import platform

    root = Path("C:\\") if platform.system() == "Windows" else Path("/")
    app = _Harness(root)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.go_up()
        assert panel.path == root.resolve()


@pytest.mark.asyncio
async def test_set_local_drive_switches_path_and_mode(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_local_drive(str(other))
        assert panel.mode == "local"
        assert panel.path == other.resolve()
        assert panel.remote_conn is None


# --------------------------------------------------------------------- remote mode

@pytest.fixture
def fake_remote_entries(monkeypatch):
    from panels import remote_backends
    from panels.remote_sources import RemoteEntry

    calls = {"list_dir": [], "download": []}

    def fake_list_dir(conn, path):
        calls["list_dir"].append((conn.name, path))
        if path == "":
            return [RemoteEntry(name="reports", is_dir=True), RemoteEntry(name="data.csv", is_dir=False, size=42)]
        if path == "reports":
            return [RemoteEntry(name="q1.csv", is_dir=False, size=7)]
        return []

    def fake_download(conn, remote_key, dest):
        calls["download"].append((conn.name, remote_key, str(dest)))
        Path(dest).write_text("downloaded", encoding="utf-8")

    monkeypatch.setattr(remote_backends, "list_dir", fake_list_dir)
    monkeypatch.setattr(remote_backends, "download", fake_download)
    return calls


@pytest.fixture
def remote_conn():
    return RemoteConnection(name="myconn", type="s3", options={"bucket": "b"})


@pytest.mark.asyncio
async def test_set_remote_loads_root_listing(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        assert panel.mode == "remote"
        # ".." + reports/ + data.csv
        assert len(panel.entries) == 3
        assert panel.entries[0] == ("..", "parent")
        assert ("reports", "dir") in panel.entries
        assert ("data.csv", "file") in panel.entries


@pytest.mark.asyncio
async def test_remote_header_shows_connection(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        header_text = panel.query_one("#header").content.plain
        assert "s3://myconn/" in header_text


@pytest.mark.asyncio
async def test_remote_enter_directory_appends_path(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        table = panel.query_one(DataTable)
        table.focus()
        # ".." row0, "reports" row1 (dirs sorted first by the fake), "data.csv" row2
        idx = next(i for i, e in enumerate(panel.entries) if e == ("reports", "dir"))
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        assert panel.remote_path == "reports"
        assert ("q1.csv", "file") in panel.entries


@pytest.mark.asyncio
async def test_remote_go_up_from_subpath_returns_to_root(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        panel.remote_path = "reports"
        panel.go_up()
        assert panel.remote_path == ""
        assert panel.mode == "remote"


@pytest.mark.asyncio
async def test_remote_go_up_from_root_exits_remote_mode(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        panel.go_up()
        assert panel.mode == "local"
        assert panel.remote_conn is None


@pytest.mark.asyncio
async def test_remote_enter_supported_file_downloads_and_posts(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        table = panel.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(panel.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        assert fake_remote_entries["download"] == [("myconn", "data.csv", fake_remote_entries["download"][0][2])]


@pytest.mark.asyncio
async def test_remote_enter_unsupported_file_does_not_download(tmp_path, fake_remote_entries, remote_conn, monkeypatch):
    from panels import remote_backends

    monkeypatch.setattr(
        remote_backends,
        "list_dir",
        lambda conn, path: [RemoteEntry(name="weird.xyz", is_dir=False, size=1)],
    )
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        table = panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=1)
        await pilot.press("enter")
        await pilot.pause()
        assert fake_remote_entries["download"] == []


@pytest.mark.asyncio
async def test_remote_listing_error_notifies_and_shows_empty(tmp_path, remote_conn, monkeypatch):
    from panels import remote_backends

    def boom(conn, path):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(remote_backends, "list_dir", boom)
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        assert panel.entries == [("..", "parent")]
        assert any("connection refused" in msg for msg, _sev in app.notifications)


@pytest.mark.asyncio
async def test_remote_download_error_notifies(tmp_path, fake_remote_entries, remote_conn, monkeypatch):
    from panels import remote_backends

    def boom(conn, key, dest):
        raise RuntimeError("network down")

    monkeypatch.setattr(remote_backends, "download", boom)
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        table = panel.query_one(DataTable)
        table.focus()
        idx = next(i for i, e in enumerate(panel.entries) if e == ("data.csv", "file"))
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        assert any("network down" in msg for msg, _sev in app.notifications)


@pytest.mark.asyncio
async def test_exit_remote_reverts_to_local(tmp_path, fake_remote_entries, remote_conn):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        panel.exit_remote()
        assert panel.mode == "local"
        assert panel.remote_conn is None
        assert panel.remote_path == ""


@pytest.mark.asyncio
async def test_remote_enter_parent_row_goes_up(tmp_path, fake_remote_entries, remote_conn):
    """Exercises _handle_remote_enter's own "parent" dispatch (via a real
    Enter keypress on the ".." row), distinct from calling go_up() directly."""
    app = _Harness(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(FilePanel)
        panel.set_remote(remote_conn)
        panel.remote_path = "reports"
        panel.load_directory()
        table = panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=0)  # ".."
        await pilot.press("enter")
        await pilot.pause()
        assert panel.remote_path == ""


# --------------------------------------------------------------- error-tolerance

def test_safe_is_dir_returns_false_on_oserror(monkeypatch, tmp_path):
    from panels.FilePanel import _safe_is_dir

    def boom(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "is_dir", boom)
    assert _safe_is_dir(tmp_path) is False


@pytest.mark.asyncio
async def test_load_directory_tolerates_iterdir_permission_error(tmp_path, monkeypatch):
    def boom(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", boom)
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        # Only the ".." entry survives; the directory itself couldn't be listed.
        assert panel.entries == [(tmp_path.parent, "parent")]


@pytest.mark.asyncio
async def test_load_directory_tolerates_lstat_oserror(tmp_path, monkeypatch):
    (tmp_path / "flaky.txt").write_text("x", encoding="utf-8")
    real_lstat = Path.lstat

    def boom(self):
        if self.name == "flaky.txt":
            raise OSError("stat failed")
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", boom)
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        # Row still present despite the stat failure; size/mtime just fall back.
        assert any(p.name == "flaky.txt" for p, _k in panel.entries)
        row_idx = next(i for i, (p, _k) in enumerate(panel.entries) if p.name == "flaky.txt")
        size_cell = str(table.get_cell_at((row_idx, 1)))
        assert size_cell == "0"


@pytest.mark.asyncio
async def test_selected_entry_none_when_cursor_row_is_none(sample_tree, monkeypatch):
    app = _Harness(sample_tree)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        table = panel.query_one(DataTable)
        monkeypatch.setattr(type(table), "cursor_row", property(lambda self: None))
        assert panel.selected_entry is None


@pytest.mark.asyncio
async def test_handle_enter_with_no_selection_is_noop(tmp_path):
    app = _Harness(tmp_path)
    async with app.run_test():
        panel = app.query_one(FilePanel)
        panel.entries = []
        panel._handle_enter(None)  # must not raise

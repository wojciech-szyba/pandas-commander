"""Tests for screens/drives.py — DriveScreen (CHNG DRV) modal."""
from __future__ import annotations

import pytest
from textual.widgets import OptionList

from panels.remote_sources import RemoteConnection
from screens.drives import DriveScreen


@pytest.fixture(autouse=True)
def fake_sources(monkeypatch):
    from panels import remote_sources

    monkeypatch.setattr(remote_sources, "list_local_drives", lambda: ["/", "/data"])
    monkeypatch.setattr(
        remote_sources,
        "list_connections",
        lambda: [RemoteConnection(name="myconn", type="s3", options={})],
    )


@pytest.mark.asyncio
async def test_drive_screen_lists_local_and_remote_options(screen_harness):
    app = screen_harness(DriveScreen)
    async with app.run_test():
        options = app.screen.query_one("#drive-list", OptionList)
        ids = [options.get_option_at_index(i).id for i in range(options.option_count)]
        assert "local:/" in ids
        assert "local:/data" in ids
        assert "remote:myconn" in ids


@pytest.mark.asyncio
async def test_drive_screen_selecting_local_dismisses_with_tuple(screen_harness):
    app = screen_harness(DriveScreen)
    async with app.run_test() as pilot:
        options = app.screen.query_one("#drive-list", OptionList)
        index = next(
            i for i in range(options.option_count) if options.get_option_at_index(i).id == "local:/data"
        )
        options.highlighted = index
        options.action_select()
        await pilot.pause()
        assert app.result == ("local", "/data")


@pytest.mark.asyncio
async def test_drive_screen_selecting_remote_dismisses_with_tuple(screen_harness):
    app = screen_harness(DriveScreen)
    async with app.run_test() as pilot:
        options = app.screen.query_one("#drive-list", OptionList)
        index = next(
            i for i in range(options.option_count) if options.get_option_at_index(i).id == "remote:myconn"
        )
        options.highlighted = index
        options.action_select()
        await pilot.pause()
        assert app.result == ("remote", "myconn")


@pytest.mark.asyncio
async def test_drive_screen_no_connections_shows_placeholder(screen_harness, monkeypatch):
    from panels import remote_sources

    monkeypatch.setattr(remote_sources, "list_connections", lambda: [])
    app = screen_harness(DriveScreen)
    async with app.run_test():
        options = app.screen.query_one("#drive-list", OptionList)
        ids = [options.get_option_at_index(i).id for i in range(options.option_count)]
        assert "_hdr_none" in ids


@pytest.mark.asyncio
async def test_drive_screen_escape_dismisses_none(screen_harness):
    app = screen_harness(DriveScreen)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


@pytest.mark.asyncio
async def test_drive_screen_focuses_option_list(screen_harness):
    app = screen_harness(DriveScreen)
    async with app.run_test():
        assert app.focused is app.screen.query_one("#drive-list", OptionList)


@pytest.mark.asyncio
async def test_drive_screen_selecting_disabled_header_does_not_dismiss(screen_harness):
    """A disabled section header ("_hdr_local"/"_hdr_remote") is unselectable
    by mouse/keyboard, but _selected()'s own id-prefix guard is what actually
    prevents a dismiss if one is ever delivered -- exercise that guard
    directly, the same way real header Option ids ("_hdr_...") are built."""
    app = screen_harness(DriveScreen)
    async with app.run_test():
        options = app.screen.query_one("#drive-list", OptionList)
        header_index = next(
            i for i in range(options.option_count) if options.get_option_at_index(i).id == "_hdr_local"
        )
        option = options.get_option_at_index(header_index)
        event = OptionList.OptionSelected(options, option, header_index)
        app.screen._selected(event)
        assert app.dismissed is False

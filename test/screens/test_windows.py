"""Tests for screens/windows.py — WindowsScreen (recent-files) modal."""
from __future__ import annotations

import pytest
from textual.widgets import Label, OptionList

from screens.windows import WindowsScreen


@pytest.mark.asyncio
async def test_windows_shows_option_per_recent_file(screen_harness):
    recent = [r"C:\a\one.csv", r"C:\a\two.py"]
    app = screen_harness(lambda: WindowsScreen(recent, current=None))
    async with app.run_test():
        options = app.screen.query_one(OptionList)
        assert options.option_count == 2


@pytest.mark.asyncio
async def test_windows_empty_recent_shows_placeholder(screen_harness):
    app = screen_harness(lambda: WindowsScreen([], current=None))
    async with app.run_test():
        assert app.screen.query_one("#windows-empty", Label).content == "(no recent files)"
        assert len(app.screen.query(OptionList)) == 0


@pytest.mark.asyncio
async def test_windows_selecting_option_dismisses_with_path(screen_harness):
    recent = [r"C:\a\one.csv", r"C:\a\two.py"]
    app = screen_harness(lambda: WindowsScreen(recent, current=None))
    async with app.run_test() as pilot:
        options = app.screen.query_one(OptionList)
        options.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == recent[0]


@pytest.mark.asyncio
async def test_windows_escape_dismisses_none(screen_harness):
    app = screen_harness(lambda: WindowsScreen([r"C:\a\one.csv"], current=None))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


@pytest.mark.asyncio
async def test_windows_focuses_option_list_when_nonempty(screen_harness):
    app = screen_harness(lambda: WindowsScreen([r"C:\a\one.csv"], current=None))
    async with app.run_test():
        assert app.focused is app.screen.query_one(OptionList)

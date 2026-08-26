"""Tests for screens/snippet_picker.py — SnippetPickerScreen modal."""
from __future__ import annotations

import pytest
from textual.widgets import Label, OptionList

from screens.snippet_picker import SnippetPickerScreen

CATALOG = {
    "read_csv": ("Read CSV", 'df = pd.read_csv("path/to/file.csv")'),
    "unique": ("Unique values", 'df["column"].unique()'),
}


@pytest.mark.asyncio
async def test_snippet_picker_shows_title_and_options(screen_harness):
    app = screen_harness(lambda: SnippetPickerScreen("Pandas snippets", CATALOG))
    async with app.run_test():
        assert app.screen.query_one(Label).content == "Pandas snippets"
        options = app.screen.query_one(OptionList)
        assert options.option_count == 2


@pytest.mark.asyncio
async def test_snippet_picker_focuses_option_list(screen_harness):
    app = screen_harness(lambda: SnippetPickerScreen("Pandas snippets", CATALOG))
    async with app.run_test():
        assert app.focused is app.screen.query_one(OptionList)


@pytest.mark.asyncio
async def test_snippet_picker_selecting_dismisses_with_code(screen_harness):
    app = screen_harness(lambda: SnippetPickerScreen("Pandas snippets", CATALOG))
    async with app.run_test() as pilot:
        await pilot.press("enter")  # first option highlighted by default
        await pilot.pause()
        assert app.result == 'df = pd.read_csv("path/to/file.csv")'


@pytest.mark.asyncio
async def test_snippet_picker_escape_dismisses_none(screen_harness):
    app = screen_harness(lambda: SnippetPickerScreen("Pandas snippets", CATALOG))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None

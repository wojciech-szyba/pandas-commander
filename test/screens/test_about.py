"""Tests for screens/about.py — AboutScreen modal."""
from __future__ import annotations

import pytest
from textual.widgets import Button, Label

from screens.about import AboutScreen


@pytest.mark.asyncio
async def test_about_shows_version_labels(screen_harness):
    app = screen_harness(lambda: AboutScreen("0.4"))
    async with app.run_test():
        title = app.screen.query_one("#about-title", Label)
        assert "0.4" in title.content
        assert app.screen.query_one("#about-version", Label).content.startswith("Textual")
        assert app.screen.query_one("#pandas-version", Label).content.startswith("Pandas")


@pytest.mark.asyncio
async def test_about_focuses_close_button(screen_harness):
    app = screen_harness(lambda: AboutScreen("0.4"))
    async with app.run_test():
        assert app.focused is app.screen.query_one("#close", Button)


@pytest.mark.asyncio
async def test_about_escape_is_not_bound_but_close_button_dismisses(screen_harness):
    app = screen_harness(lambda: AboutScreen("0.4"))
    async with app.run_test() as pilot:
        await pilot.click("#close")
        await pilot.pause()
        assert app.dismissed is True
        assert app.result is None


@pytest.mark.asyncio
async def test_about_action_close_dismisses_with_none(screen_harness):
    app = screen_harness(lambda: AboutScreen("0.4"))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.dismissed is True
        assert app.result is None

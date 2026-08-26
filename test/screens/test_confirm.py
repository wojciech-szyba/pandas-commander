"""Tests for screens/confirm.py — ConfirmScreen yes/no modal."""
from __future__ import annotations

import pytest
from textual.widgets import Button, Label

from screens.confirm import ConfirmScreen


@pytest.mark.asyncio
async def test_confirm_shows_question(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete 'x'?"))
    async with app.run_test():
        assert app.screen.query_one(Label).content == "Delete 'x'?"


@pytest.mark.asyncio
async def test_confirm_focuses_no_button_by_default(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test():
        assert app.focused is app.screen.query_one("#no", Button)


@pytest.mark.asyncio
async def test_confirm_y_key_dismisses_true(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test() as pilot:
        await pilot.press("y")
        await pilot.pause()
        assert app.result is True


@pytest.mark.asyncio
async def test_confirm_n_key_dismisses_false(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        assert app.result is False


@pytest.mark.asyncio
async def test_confirm_escape_dismisses_false(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is False


@pytest.mark.asyncio
async def test_confirm_yes_button_dismisses_true(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test() as pilot:
        await pilot.click("#yes")
        await pilot.pause()
        assert app.result is True


@pytest.mark.asyncio
async def test_confirm_no_button_dismisses_false(screen_harness):
    app = screen_harness(lambda: ConfirmScreen("Delete?"))
    async with app.run_test() as pilot:
        await pilot.click("#no")
        await pilot.pause()
        assert app.result is False

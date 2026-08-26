"""Tests for screens/prompt.py — PromptScreen single-line text input modal."""
from __future__ import annotations

import pytest
from textual.widgets import Input, Label

from screens.prompt import PromptScreen


@pytest.mark.asyncio
async def test_prompt_shows_label_and_default_value(screen_harness):
    app = screen_harness(lambda: PromptScreen("New directory name:", default="foo"))
    async with app.run_test():
        assert app.screen.query_one(Label).content == "New directory name:"
        assert app.screen.query_one(Input).value == "foo"


@pytest.mark.asyncio
async def test_prompt_focuses_input(screen_harness):
    app = screen_harness(lambda: PromptScreen("Name:"))
    async with app.run_test():
        assert app.focused is app.screen.query_one(Input)


@pytest.mark.asyncio
async def test_prompt_submit_dismisses_with_value(screen_harness):
    app = screen_harness(lambda: PromptScreen("Name:"))
    async with app.run_test() as pilot:
        await pilot.click(Input)
        await pilot.press(*"newname")
        await pilot.press("enter")
        await pilot.pause()
        assert app.dismissed is True
        assert app.result == "newname"


@pytest.mark.asyncio
async def test_prompt_escape_dismisses_none(screen_harness):
    app = screen_harness(lambda: PromptScreen("Name:"))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.dismissed is True
        assert app.result is None


@pytest.mark.asyncio
async def test_prompt_submit_empty_dismisses_with_empty_string(screen_harness):
    app = screen_harness(lambda: PromptScreen("Name:"))
    async with app.run_test() as pilot:
        await pilot.click(Input)
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == ""

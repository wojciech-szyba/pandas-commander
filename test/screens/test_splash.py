"""Tests for screens/splash.py — SplashScreen (startup banner)."""
from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from screens.splash import SplashScreen


class _Harness(App):
    def compose(self) -> ComposeResult:
        return
        yield

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())


@pytest.mark.asyncio
async def test_splash_shows_art_and_hint():
    app = _Harness()
    async with app.run_test():
        assert app.screen.query_one("#splash-art", Static).content
        assert "Press any key" in app.screen.query_one("#splash-hint", Static).content


@pytest.mark.asyncio
async def test_splash_any_key_dismisses():
    app = _Harness()
    async with app.run_test() as pilot:
        assert len(app.screen_stack) == 2  # default screen + splash
        await pilot.press("x")
        await pilot.pause()
        assert len(app.screen_stack) == 1


@pytest.mark.asyncio
async def test_splash_timer_dismisses_after_timeout():
    app = _Harness()
    async with app.run_test():
        splash = app.screen
        assert isinstance(splash, SplashScreen)
        splash._dismiss()
        assert app.screen is not splash

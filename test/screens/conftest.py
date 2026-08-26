"""Shared harness for modal-screen tests: a minimal App that pushes the
screen under test and records what it's dismissed with."""
from __future__ import annotations

from typing import Callable

import pytest
from textual.app import App, ComposeResult
from textual.screen import Screen


class ScreenHarness(App):
    """Pushes `screen_factory()` on mount and records the dismiss() result."""

    _SENTINEL = object()

    def __init__(self, screen_factory: Callable[[], Screen]):
        super().__init__()
        self._screen_factory = screen_factory
        self.result = self._SENTINEL
        self.dismissed = False

    def compose(self) -> ComposeResult:
        return
        yield  # pragma: no cover - makes this a generator with no widgets

    def on_mount(self) -> None:
        def done(result=None) -> None:
            self.result = result
            self.dismissed = True

        self.push_screen(self._screen_factory(), done)


@pytest.fixture
def screen_harness():
    return ScreenHarness

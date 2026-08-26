"""Tests for screens/command_output.py — CommandOutputScreen modal.

The real subprocess machinery (asyncio.create_subprocess_shell) is stubbed
out with a fake process so these tests are fast, deterministic, and don't
depend on the host shell (cmd.exe vs POSIX sh).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import RichLog, Static

from screens import command_output as co
from screens.command_output import CommandOutputScreen


class _FakeStdout:
    """Yields `lines` then blocks (as a still-running process's pipe would)
    until the process is killed, at which point it reports EOF -- exactly
    like a real pipe closing when its writer process is terminated."""

    def __init__(self, lines: list[bytes], process: "_FakeProcess"):
        self._lines = list(lines)
        self._index = 0
        self._process = process

    async def readline(self) -> bytes:
        if self._index < len(self._lines):
            line = self._lines[self._index]
            self._index += 1
            await asyncio.sleep(0)  # yield control, like a real async pipe read
            return line
        if self._process.blocks_at_eof:
            # Simulates a still-running process: the pipe only closes on kill().
            await self._process.eof_event.wait()
        return b""


class _FakeProcess:
    def __init__(self, lines: list[bytes], returncode: int = 0, blocks_at_eof: bool = False):
        self.stdout = _FakeStdout(lines, self)
        self.returncode = None
        self._final_returncode = returncode
        self.killed = False
        self.blocks_at_eof = blocks_at_eof
        self.eof_event = asyncio.Event()

    async def wait(self) -> int:
        self.returncode = self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.eof_event.set()


@pytest.mark.asyncio
async def test_command_output_streams_lines_and_shows_exit_code(monkeypatch):
    fake = _FakeProcess([b"line one\n", b"line two\n"], returncode=0)

    async def fake_create_subprocess_shell(*args, **kwargs):
        return fake

    monkeypatch.setattr(co.asyncio, "create_subprocess_shell", fake_create_subprocess_shell)

    app_screen = CommandOutputScreen("echo hi", Path("."))
    from textual.app import App, ComposeResult

    class Harness(App):
        def compose(self) -> ComposeResult:
            return
            yield

        def on_mount(self) -> None:
            self.push_screen(app_screen)

    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        log_text = "\n".join(str(line) for line in app.screen.query_one(RichLog).lines)
        assert "line one" in log_text
        assert "line two" in log_text
        status = app.screen.query_one("#cmd-status", Static).content
        assert "Exited with code 0" in status


@pytest.mark.asyncio
async def test_command_output_shows_title_with_command():
    from textual.app import App, ComposeResult

    async def fake_create_subprocess_shell(*args, **kwargs):
        return _FakeProcess([], returncode=0)

    screen = CommandOutputScreen("ls -la", Path("."))

    class Harness(App):
        def compose(self) -> ComposeResult:
            return
            yield

        def on_mount(self) -> None:
            self.push_screen(screen)

    import unittest.mock

    with unittest.mock.patch.object(co.asyncio, "create_subprocess_shell", fake_create_subprocess_shell):
        app = Harness()
        async with app.run_test() as pilot:
            await pilot.pause()
            title = app.screen.query_one("#cmd-title", Static).content
            assert "ls -la" in title


@pytest.mark.asyncio
async def test_command_output_error_creating_process_shows_failure(monkeypatch):
    async def boom(*args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(co.asyncio, "create_subprocess_shell", boom)

    from textual.app import App, ComposeResult

    screen = CommandOutputScreen("nonexistent-cmd", Path("."))

    class Harness(App):
        def compose(self) -> ComposeResult:
            return
            yield

        def on_mount(self) -> None:
            self.push_screen(screen)

    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        log_text = "\n".join(str(line) for line in app.screen.query_one(RichLog).lines)
        assert "Error" in log_text
        assert "command not found" in log_text
        status = app.screen.query_one("#cmd-status", Static).content
        assert "Failed to run" in status


@pytest.mark.asyncio
async def test_command_output_close_kills_running_process(monkeypatch):
    fake = _FakeProcess([b"still going\n"], returncode=0, blocks_at_eof=True)

    async def fake_create_subprocess_shell(*args, **kwargs):
        return fake

    monkeypatch.setattr(co.asyncio, "create_subprocess_shell", fake_create_subprocess_shell)

    from textual.app import App, ComposeResult

    screen = CommandOutputScreen("tail -f something", Path("."))
    result = {}

    class Harness(App):
        def compose(self) -> ComposeResult:
            return
            yield

        def on_mount(self) -> None:
            def done(value):
                result["value"] = value

            self.push_screen(screen, done)

    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen._process = fake  # ensure the worker's process reference is visible
        screen.action_close()
        await pilot.pause()
        assert fake.killed is True
        assert result.get("value") is None


@pytest.mark.asyncio
async def test_command_output_close_after_finished_does_not_kill(monkeypatch):
    fake = _FakeProcess([], returncode=0)

    async def fake_create_subprocess_shell(*args, **kwargs):
        return fake

    monkeypatch.setattr(co.asyncio, "create_subprocess_shell", fake_create_subprocess_shell)

    from textual.app import App, ComposeResult

    screen = CommandOutputScreen("echo done", Path("."))

    class Harness(App):
        def compose(self) -> ComposeResult:
            return
            yield

        def on_mount(self) -> None:
            self.push_screen(screen)

    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # Process has already run to completion (returncode set by wait()).
        assert fake.returncode == 0
        screen.action_close()
        assert fake.killed is False

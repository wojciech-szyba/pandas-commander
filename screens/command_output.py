import asyncio
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import (
    RichLog,
    Static
)
from pathlib import Path
import contextlib


class CommandOutputScreen(ModalScreen[None]):
    """Runs a shell command and streams its stdout/stderr live; closable any time."""

    CSS = """
    CommandOutputScreen { align: center middle; }
    #cmd-dialog {
        width: 90%;
        height: 80%;
        padding: 0 1;
        border: thick $accent;
        background: $surface;
    }
    #cmd-title {
        height: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #cmd-log { height: 1fr; }
    #cmd-status { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+c", "close", "Close"),
    ]

    def __init__(self, command: str, cwd: Path) -> None:
        super().__init__()
        self.command = command
        self.cwd = cwd
        self._process: asyncio.subprocess.Process | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="cmd-dialog"):
            yield Static(f" $ {self.command}", id="cmd-title")
            yield RichLog(id="cmd-log", wrap=True, highlight=False, markup=False)
            yield Static("Running…  (Esc to close)", id="cmd-status")

    def on_mount(self) -> None:
        self.query_one("#cmd-log", RichLog).focus()
        self.run_worker(self._run(), exclusive=True)

    async def _run(self) -> None:
        log = self.query_one("#cmd-log", RichLog)
        status = self.query_one("#cmd-status", Static)
        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                cwd=str(self.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._process = process
            assert process.stdout is not None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                log.write(line.decode(errors="replace").rstrip("\n"))
            returncode = await process.wait()
            status.update(f"Exited with code {returncode}  (Esc to close)")
        except Exception as exc:  # noqa: BLE001
            log.write(f"Error: {exc}")
            status.update("Failed to run  (Esc to close)")
        finally:
            self._process = None

    def action_close(self) -> None:
        if self._process is not None and self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
        self.dismiss(None)

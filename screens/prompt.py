from textual.screen import ModalScreen
from textual.binding import Binding
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import (
    Input,
    Label
)
from textual import on

class PromptScreen(ModalScreen[str | None]):
    """Single-line text prompt (used for mkdir, rename, etc.)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, default: str = "") -> None:
        super().__init__()
        self.prompt = prompt
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.prompt)
            yield Input(value=self.default, id="prompt-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

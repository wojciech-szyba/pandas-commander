from textual.screen import ModalScreen
from textual.binding import Binding
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import (
    Label,
    OptionList
)
from textual.widgets.option_list import Option
from pathlib import Path
from rich.text import Text
from textual import on

class WindowsScreen(ModalScreen[str | None]):
    """List of open/recent files; Enter opens the highlighted one."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, recent: list[str], current: str | None) -> None:
        super().__init__()
        self.recent = recent
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Open / recent files")
            if self.recent:
                options: list[Option] = []
                for p in self.recent:
                    marker = "● " if p == self.current else "  "
                    label = Text(f"{marker}{Path(p).name}", no_wrap=True)
                    label.append(f"   {p}", style="dim")
                    options.append(Option(label, id=p))
                yield OptionList(*options, id="windows-list")
            else:
                yield Label("(no recent files)", id="windows-empty")

    def on_mount(self) -> None:
        if self.recent:
            self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)

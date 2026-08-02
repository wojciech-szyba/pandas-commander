from textual.screen import ModalScreen
from textual.binding import Binding
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import (
    Label,
    OptionList,
)
from textual.widgets.option_list import Option
from textual import on


class SnippetPickerScreen(ModalScreen[str | None]):
    """List of snippets for one library (pandas/polars/pyspark/dbt); Enter inserts
    the highlighted one. Dismisses with the snippet code, or None if cancelled."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, snippets: dict[str, tuple[str, str]]) -> None:
        super().__init__()
        self.title_text = title
        self.snippets = snippets

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.title_text)
            options = [Option(label, id=key) for key, (label, _code) in self.snippets.items()]
            yield OptionList(*options, id="snippet-list")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        _label, code = self.snippets[event.option.id]
        self.dismiss(code)

    def action_cancel(self) -> None:
        self.dismiss(None)

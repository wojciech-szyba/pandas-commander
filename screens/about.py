from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Label
)
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual import on
from textual import __version__ as textual_version
from pandas import __version__ as pandas_version

class AboutScreen(ModalScreen[None]):
    """Simple About dialog with app info."""

    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, app_ver:str):
        self.app_ver = app_ver
        super(AboutScreen, self).__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Pandas Commander v. {self.app_ver}", id="about-title")
            yield Label("A terminal file commander for exploring, editing and\nquerying data with pandas and more.\n")
            yield Label("Composed by Wojciech Szyba 2026")
            yield Label("https://github.com/wojciech-szyba/pandas-commander)")
            yield Label(f"Textual {textual_version}", id="about-version")
            yield Label(f"Pandas {pandas_version}", id="pandas-version")
            with Horizontal(id="buttons"):
                yield Button("Close", variant="primary", id="close")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
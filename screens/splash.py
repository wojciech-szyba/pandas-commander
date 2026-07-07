from textual.screen import Screen
from textual.widgets import Static
from textual.app import ComposeResult
from pathlib import Path

class SplashScreen(Screen):
    CSS = """
    SplashScreen {
        align: center middle;
        background: $surface;
    }
    #splash-art {
        width: auto;
        height: auto;
        content-align: center middle;
        color: $accent;
    }
    #splash-hint {
        dock: bottom;
        height: 1;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        splash_path = Path(__file__).parent / "splash.txt"
        yield Static(splash_path.read_text(), id="splash-art")
        yield Static("Press any key to continue…", id="splash-hint")

    def on_mount(self) -> None:
        self.set_timer(5.0, self._dismiss)

    def on_key(self) -> None:
        self._dismiss()

    def _dismiss(self) -> None:
        self.app.pop_screen()

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from panels.EditorPanel import EditorPanel
from panels.FilePanel import FilePanel
from datetime import datetime
from pathlib import Path

from rich.text import Text

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    OptionList,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option


# -------------------------------------------------------------------- splash
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


# --------------------------------------------------------------------- modals
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


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    BINDINGS = [
        Binding("escape", "no", "Cancel"),
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.question)
            with Horizontal(id="buttons"):
                yield Button("Yes", variant="error", id="yes")
                yield Button("No", variant="primary", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_no(self) -> None:
        self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)


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


# ----------------------------------------------------------------------- app
class PandasCommander(App):
    CSS = """
    Screen { background: $surface; }

    #panels { height: 1fr; }

    FilePanel {
        width: 30%;
        border: round $primary;
        margin: 0 0;
    }
    FilePanel.-active { border: double $accent; }

    FilePanel > #header {
        height: 1;
        width: 100%;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    FilePanel.-active > #header { background: $accent; }

    DataTable { height: 1fr; }

    EditorPanel {
        width: 70%;
        border: round $primary;
        margin: 0 0;
    }
    EditorPanel.-active { border: double $accent; }

    EditorPanel > #ep-header {
        height: 1;
        width: 100%;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    EditorPanel.-active > #ep-header { background: $accent; }

    EditorPanel > #ep-placeholder {
        height: 1fr;
        content-align: center middle;
    }

    EditorPanel > #ep-area { height: 1fr; }

    EditorPanel > #ep-result-header {
        height: 1;
        background: $primary-darken-1;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }

    EditorPanel > #ep-result-table { height: 1fr; }

    #cmdline {
        height: 3;
        dock: bottom;
        border: round $primary;
    }

    /* modal dialogs */
    PromptScreen, ConfirmScreen, WindowsScreen { align: center middle; }
    WindowsScreen #dialog { width: 90; }
    #windows-list { height: auto; max-height: 20; margin-top: 1; }
    #dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #buttons { height: auto; align-horizontal: center; margin-top: 1; }
    #buttons Button { margin: 0 1; }
    
    #viewer-title, #editor-title { height: 1; }
    """

    BINDINGS = [
        Binding("tab", "switch_panel", "Switch", priority=True),
        Binding("backspace", "up", "Up"),
        Binding("f2", "windows", "Windows"),
        Binding("f4", "pandas_canvas", "Open in Pandas"),
        Binding("f7", "mkdir", "MkDir"),
        Binding("f8", "delete", "Delete"),
        Binding("ctrl+l", "focus_cmd", "Cmd"),
        Binding("f10", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    # Where the recent-files list is persisted between sessions.
    RECENT_PATH = Path.home() / ".pandas_commander_recent.json"
    MAX_RECENT = 20

    def __init__(self, start_dir: str | None = None) -> None:
        super().__init__()
        self.start_dir = start_dir or os.getcwd()
        self.active_panel: FilePanel | None = None
        self.recent_files: list[str] = self._load_recent()

    def compose(self) -> ComposeResult:
        with Horizontal(id="panels"):
            yield FilePanel(self.start_dir, panel_id="left")
            yield EditorPanel()
        yield Input(placeholder="Shell command — runs in active panel's dir…", id="cmdline")
        yield Footer()

    def on_mount(self) -> None:
        self.left = self.query_one("#left", FilePanel)
        self.right = self.query_one("#right", EditorPanel)
        self.set_active(self.left)
        self.left.query_one(DataTable).focus()
        self.push_screen(SplashScreen())

    # ------------------------------------------------------------- panel state
    def set_active(self, panel: FilePanel) -> None:
        if self.active_panel is panel:
            return
        if self.active_panel is not None:
            self.active_panel.remove_class("-active")
        self.right.remove_class("-active")
        self.active_panel = panel
        panel.add_class("-active")



    def refresh_panels(self) -> None:
        self.left.load_directory()

    def on_descendant_focus(self, event) -> None:
        node = event.widget
        while node is not None:
            if isinstance(node, FilePanel):
                self.set_active(node)
                self.right.remove_class("-active")
                return
            if isinstance(node, EditorPanel):
                if self.active_panel is not None:
                    self.active_panel.remove_class("-active")
                self.right.add_class("-active")
                return
            node = node.parent

    # ----------------------------------------------------------------- actions
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("pandas_canvas", "mkdir", "delete"):
            node = self.focused
            while node is not None:
                if isinstance(node, EditorPanel):
                    return None
                node = node.parent
        return True

    def action_switch_panel(self) -> None:
        area = self.right.query_one("#ep-area", TextArea)
        focused = self.focused
        in_editor = False
        node = focused
        while node is not None:
            if isinstance(node, EditorPanel):
                in_editor = True
                break
            node = node.parent
        if in_editor:
            self.left.query_one(DataTable).focus()
        elif area.display:
            area.focus()

    def action_up(self) -> None:
        if self.active_panel:
            self.active_panel.go_up()

    def action_focus_cmd(self) -> None:
        self.query_one("#cmdline", Input).focus()

    def action_windows(self) -> None:
        recent = [p for p in self.recent_files if Path(p).exists()]
        current = str(self.right.current_path) if self.right.current_path else None

        def done(chosen: str | None) -> None:
            if chosen:
                self.open_file(Path(chosen))

        self.push_screen(WindowsScreen(recent, current), done)

    def action_mkdir(self) -> None:
        panel = self.active_panel
        if panel is None:
            return

        def done(name: str | None) -> None:
            if not name:
                return
            try:
                (panel.path / name).mkdir(parents=True, exist_ok=False)
                self.refresh_panels()
                self.notify(f"Created {name}")
            except OSError as exc:
                self.notify(f"mkdir failed: {exc}", severity="error")

        self.push_screen(PromptScreen("New directory name:"), done)

    def action_delete(self) -> None:
        entry = self._selected_real()
        if entry is None:
            return
        path, kind = entry

        def done(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                if kind == "dir":
                    shutil.rmtree(path)
                else:
                    path.unlink()
                self.refresh_panels()
                self.notify(f"Deleted {path.name}")
            except OSError as exc:
                self.notify(f"Delete failed: {exc}", severity="error")

        self.push_screen(ConfirmScreen(f"Delete '{path.name}'?  This cannot be undone."), done)

    def action_pandas_canvas(self) -> None:
        entry = self._selected_real()
        if entry is None:
            return
        path, kind = entry

        if kind != "dir":
            new_path = path.with_suffix(".pandas")
            if not new_path.exists():
                new_path.touch()
                with open(new_path, 'w') as f:
                    f.write('import pandas as pd\n\n')
                    *_, extension = path.name.split('.')
                    if extension == 'csv':
                        f.write(f'df = pd.read_csv("{path}")\n')
                    elif extension == 'parquet':
                        f.write(f'df = pd.read_parquet("{path}")\n')
                    f.write('\nprint(df.head())\n')
            self.open_file(new_path)

    # -------------------------------------------------------- file panel event
    @on(FilePanel.FileSelected)
    def _on_file_selected(self, event: FilePanel.FileSelected) -> None:
        self.open_file(event.path)

    # ------------------------------------------------------------- command line
    @on(Input.Submitted, "#cmdline")
    def _run_command(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""
        if not cmd:
            return
        cwd = self.active_panel.path if self.active_panel else Path.cwd()
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=str(cwd),
                capture_output=True, text=True, timeout=30,
            )
            output = (result.stdout or "") + (result.stderr or "")
            output = output or "(no output)"
        except Exception as exc:  # noqa: BLE001
            output = f"Error: {exc}"
        self.refresh_panels()
        if self.active_panel:
            self.active_panel.query_one(DataTable).focus()

    # ------------------------------------------------------------ open / recent
    def open_file(self, path: Path) -> None:
        """Open a file in the editor, record it as recent, and offer autosave recovery."""
        self.add_recent(path)
        self.right.load_file(path)
        recovered = self.right.check_autosave_recovery()
        if recovered is not None:
            def done(yes: bool | None) -> None:
                if yes:
                    self.right.apply_recovered_text(recovered)
                    self.notify("Recovered unsaved changes.")
                else:
                    self.right.discard_autosave()

            self.push_screen(
                ConfirmScreen(
                    f"Unsaved changes found for '{path.name}'. Recover them?"
                ),
                done,
            )

    def add_recent(self, path: Path) -> None:
        try:
            s = str(path.resolve())
        except OSError:
            s = str(path)
        self.recent_files = [s] + [p for p in self.recent_files if p != s]
        del self.recent_files[self.MAX_RECENT:]
        self._save_recent()

    def _load_recent(self) -> list[str]:
        try:
            data = json.loads(self.RECENT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(p) for p in data]
        except (OSError, ValueError):
            pass
        return []

    def _save_recent(self) -> None:
        try:
            self.RECENT_PATH.write_text(json.dumps(self.recent_files), encoding="utf-8")
        except OSError:
            pass

    # ----------------------------------------------------------------- helpers
    def _selected_file(self) -> tuple[Path, str] | None:
        entry = self.active_panel.selected_entry if self.active_panel else None
        if entry is None or entry[1] != "file":
            self.notify("Select a file first.", severity="warning")
            return None
        return entry

    def _selected_real(self) -> tuple[Path, str] | None:
        """Selected entry that is a real file or dir (not '..')."""
        entry = self.active_panel.selected_entry if self.active_panel else None
        if entry is None or entry[1] == "parent":
            self.notify("Nothing to operate on.", severity="warning")
            return None
        return entry


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    PandasCommander(start_dir=start).run()


if __name__ == "__main__":
    main()

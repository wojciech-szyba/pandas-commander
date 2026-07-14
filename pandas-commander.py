from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
from panels import formats, remote_backends, remote_sources
from panels.EditorPanel import EditorPanel
from panels.FilePanel import FilePanel
from screens.splash import SplashScreen
from screens.prompt import PromptScreen
from screens.confirm import ConfirmScreen
from screens.command_output import CommandOutputScreen
from screens.windows import WindowsScreen
from screens.about import AboutScreen
from screens.drives import DriveScreen
from screens.directory_picker import DirectoryPickerScreen
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
    RichLog,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

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
    PromptScreen, ConfirmScreen, WindowsScreen, AboutScreen, DriveScreen, DirectoryPickerScreen { align: center middle; }
    WindowsScreen #dialog { width: 90; }
    #windows-list { height: auto; max-height: 20; margin-top: 1; }
    DriveScreen #dialog { width: 70; }
    #drive-list { height: auto; max-height: 20; margin-top: 1; }
    DirectoryPickerScreen #dialog { width: 80; height: 30; }
    #picker-path { color: $text-muted; margin-top: 1; }
    #picker-tree { height: 1fr; margin-top: 1; border: round $primary; }
    #dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #buttons { height: auto; align-horizontal: center; margin-top: 1; }
    #buttons Button { margin: 0 1; }
    #about-title { text-style: bold; color: $accent; margin-bottom: 1; }
    #about-version { color: $text-muted; margin-top: 1; }
    #pandas-version { color: $text-muted; margin-top: 1; }
    
    #viewer-title, #editor-title { height: 1; }
    """

    BINDINGS = [
        Binding("tab", "switch_panel", "Switch", priority=True),
        Binding("backspace", "up", "Up"),
        Binding("f1", "about", "About"),
        Binding("f2", "windows", "Windows"),
        Binding("f4", "pandas_canvas", "Open in Pandas"),
        Binding("f5", "new_file", "New"),
        Binding("f6", "chng_drv", "ChngDrv"),
        Binding("f7", "mkdir", "MkDir"),
        Binding("f8", "delete", "Delete"),
        Binding("f3", "copy_file", "Copy"),
        Binding("f9", "move_file", "Move"),
        Binding("f11", "download_file", "Download"),
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
        if action in ("pandas_canvas", "mkdir", "delete", "new_file", "copy_file", "move_file"):
            node = self.focused
            while node is not None:
                if isinstance(node, EditorPanel):
                    return None
                node = node.parent
            if self.active_panel is not None and self.active_panel.mode == "remote":
                # Remote sources are a read-only preview; no write operations there.
                return None
        if action == "download_file":
            node = self.focused
            while node is not None:
                if isinstance(node, EditorPanel):
                    return None
                node = node.parent
            if self.active_panel is None or self.active_panel.mode != "remote":
                # Download only makes sense from a remote source.
                return None
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

    def action_about(self) -> None:
        self.push_screen(AboutScreen('0.4'))

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

    def action_new_file(self) -> None:
        panel = self.active_panel
        if panel is None:
            return

        def done(name: str | None) -> None:
            if not name:
                return
            new_path = panel.path / name
            if new_path.exists():
                self.notify(f"'{name}' already exists", severity="warning")
                return
            try:
                new_path.touch(exist_ok=False)
                self.refresh_panels()
                self.notify(f"Created {name}")
            except OSError as exc:
                self.notify(f"Create failed: {exc}", severity="error")

        self.push_screen(PromptScreen("New file name (with extension):"), done)

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

    def action_chng_drv(self) -> None:
        panel = self.active_panel
        if panel is None:
            return

        def done(choice: tuple[str, str] | None) -> None:
            if choice is None:
                return
            kind, value = choice
            if kind == "local":
                panel.set_local_drive(value)
                return
            conn = next((c for c in remote_sources.list_connections() if c.name == value), None)
            if conn is None:
                self.notify(f"Remote connection '{value}' not found in remote.ini.", severity="error")
                return
            panel.set_remote(conn)

        self.push_screen(DriveScreen(), done)

    def action_copy_file(self) -> None:
        self._transfer_local(move=False)

    def action_move_file(self) -> None:
        self._transfer_local(move=True)

    def _transfer_local(self, move: bool) -> None:
        entry = self._selected_real()
        if entry is None:
            return
        path, kind = entry
        verb, verb_past = ("Move", "Moved") if move else ("Copy", "Copied")

        def done(dest_dir: Path | None) -> None:
            if dest_dir is None:
                return
            try:
                if move:
                    shutil.move(str(path), str(dest_dir))
                elif kind == "dir":
                    shutil.copytree(path, dest_dir / path.name)
                else:
                    shutil.copy2(path, dest_dir)
                self.refresh_panels()
                self.notify(f"{verb_past} '{path.name}' to {dest_dir}")
            except (OSError, shutil.Error) as exc:
                self.notify(f"{verb} failed: {exc}", severity="error")

        self.push_screen(
            DirectoryPickerScreen(Path(path.anchor), f"{verb} '{path.name}' to:"), done
        )

    def action_download_file(self) -> None:
        panel = self.active_panel
        if panel is None or panel.mode != "remote":
            return
        entry = self._selected_real()
        if entry is None:
            return
        name, kind = entry
        if kind != "file":
            self.notify("Select a file to download.", severity="warning")
            return
        conn = panel.remote_conn
        remote_key = f"{panel.remote_path}/{name}" if panel.remote_path else name

        def done(dest_dir: Path | None) -> None:
            if dest_dir is None:
                return
            dest = dest_dir / name
            try:
                remote_backends.download(conn, remote_key, dest)
                self.notify(f"Downloaded '{name}' to {dest_dir}")
            except Exception as exc:  # noqa: BLE001 - surface any backend/auth/network error
                self.notify(f"Download failed: {exc}", severity="error")

        self.push_screen(
            DirectoryPickerScreen(Path(Path.home().anchor), f"Download '{name}' to:"), done
        )

    def action_pandas_canvas(self) -> None:
        entry = self._selected_real()
        if entry is None:
            return
        path, kind = entry

        if kind != "dir":
            base = path
            # data.csv.gz -> data.pandas (drop the compression suffix first).
            if base.suffix.lower() in formats.COMPRESSIONS and Path(base.stem).suffix:
                base = base.with_suffix("")
            new_path = base.with_suffix(".pandas")
            if not new_path.exists():
                new_path.touch()
                with open(new_path, 'w') as f:
                    f.write('import pandas as pd\n\n')
                    f.write(formats.read_code(path) + '\n')
                    f.write(formats.read_df_head(path))
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

        def done(_: None) -> None:
            self.refresh_panels()
            if self.active_panel:
                self.active_panel.query_one(DataTable).focus()

        self.push_screen(CommandOutputScreen(cmd, cwd), done)

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

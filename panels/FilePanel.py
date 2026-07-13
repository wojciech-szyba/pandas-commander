from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.text import Text

from panels import formats

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.binding import Binding
from textual.message import Message
from textual.widgets import (
    DataTable,
    Static,
)

def _safe_is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False

def human_size(num: int) -> str:
    """Render a byte count with thousands separators."""
    return f"{num:,}"
    

# ------------------------------------------------------------------ FilePanel
class FilePanel(Vertical):
    """Left pane: path header + DataTable directory listing."""

    SUPPORTED_SUFFIXES = (
        {".py", ".pandas", ".polars", ".sql"} | set(formats.FORMATS) | set(formats.COMPRESSIONS)
    )

    BINDINGS = [

    ]

    class FileSelected(Message):
        """Posted when the user presses Enter on a supported file type."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    def __init__(self, start_path: str | Path, panel_id: str) -> None:
        super().__init__(id=panel_id)
        self.path = Path(start_path).expanduser().resolve()
        self.entries: list[tuple[Path, str]] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        table = DataTable(id="table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Name", width=None)
        table.add_column("Size", width=12)
        table.add_column("Modified", width=16)
        self.load_directory()

    # ------------------------------------------------------------------ data
    def load_directory(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self.entries = []

        header = self.query_one("#header", Static)
        header.update(Text(f" {self.path} ", overflow="ellipsis", no_wrap=True))

        rows: list[tuple[Text, Text, Text]] = []

        if self.path.parent != self.path:
            self.entries.append((self.path.parent, "parent"))
            rows.append((
                Text("..", style="bold yellow"),
                Text("<UP>", justify="right", style="yellow"),
                Text(""),
            ))

        try:
            items = sorted(
                self.path.iterdir(),
                key=lambda p: (not _safe_is_dir(p), p.name.lower()),
            )
        except (PermissionError, OSError):
            items = []

        for item in items:
            # Hide editor autosave sidecars (.name.autosave) from the listing.
            if item.name.endswith(".autosave"):
                continue
            is_dir = _safe_is_dir(item)
            try:
                st = item.lstat()
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                size = st.st_size
            except OSError:
                mtime, size = "?", 0

            if is_dir:
                self.entries.append((item, "dir"))
                name = Text(f"{item.name}/", style="bold cyan")
                size_text = Text("<DIR>", justify="right", style="cyan")
            else:
                self.entries.append((item, "file"))
                if item.suffix.lower() in self.SUPPORTED_SUFFIXES:
                    name = Text(item.name, style="bold green")
                else:
                    name = Text(item.name)
                size_text = Text(human_size(size), justify="right")
            rows.append((name, size_text, Text(mtime, style="dim")))

        for row in rows:
            table.add_row(*row)
        if table.row_count:
            table.move_cursor(row=0)

    @property
    def selected_entry(self) -> tuple[Path, str] | None:
        table = self.query_one(DataTable)
        if not self.entries:
            return None
        idx = table.cursor_row
        if idx is None or not (0 <= idx < len(self.entries)):
            return None
        return self.entries[idx]

    def go_up(self) -> None:
        if self.path.parent != self.path:
            self.path = self.path.parent
            self.load_directory()

    # ----------------------------------------------------------------- events
    @on(DataTable.RowSelected)
    def _handle_enter(self, event: DataTable.RowSelected) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        path, kind = entry
        if kind in ("parent", "dir"):
            self.path = path.resolve()
            self.load_directory()
        elif kind == "file" and path.suffix.lower() in self.SUPPORTED_SUFFIXES:
            self.post_message(self.FileSelected(path))

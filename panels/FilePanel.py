from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from rich.text import Text

from panels import formats, remote_backends
from panels.remote_sources import RemoteConnection

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
        self.entries: list[tuple[Path | str, str]] = []
        # "local" browses self.path; "remote" browses remote_conn at remote_path
        # (a '/'-joined key/prefix, '' meaning the connection's root).
        self.mode: str = "local"
        self.remote_conn: RemoteConnection | None = None
        self.remote_path: str = ""

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
        if self.mode == "remote":
            self._load_remote_directory()
        else:
            self._load_local_directory()

    def _load_local_directory(self) -> None:
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

    def _load_remote_directory(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self.entries = []

        conn = self.remote_conn
        header = self.query_one("#header", Static)
        header.update(Text(f" {conn.type}://{conn.name}/{self.remote_path} ", overflow="ellipsis", no_wrap=True))

        rows: list[tuple[Text, Text, Text]] = []

        # ".." always present: steps up a level, or exits remote mode at the root.
        self.entries.append(("..", "parent"))
        rows.append((
            Text("..", style="bold yellow"),
            Text("<UP>", justify="right", style="yellow"),
            Text(""),
        ))

        try:
            remote_entries = remote_backends.list_dir(conn, self.remote_path)
        except Exception as exc:  # noqa: BLE001 - surface any backend/auth/network error
            self.app.notify(f"Remote listing failed: {exc}", severity="error")
            remote_entries = []

        for item in remote_entries:
            if item.is_dir:
                self.entries.append((item.name, "dir"))
                name = Text(f"{item.name}/", style="bold cyan")
                size_text = Text("<DIR>", justify="right", style="cyan")
            else:
                self.entries.append((item.name, "file"))
                suffix = Path(item.name).suffix.lower()
                name = Text(item.name, style="bold green" if suffix in self.SUPPORTED_SUFFIXES else "")
                size_text = Text(human_size(item.size), justify="right")
            rows.append((name, size_text, Text("", style="dim")))

        for row in rows:
            table.add_row(*row)
        if table.row_count:
            table.move_cursor(row=0)

    # --------------------------------------------------------------- drives
    def set_local_drive(self, drive: str) -> None:
        self.mode = "local"
        self.remote_conn = None
        self.remote_path = ""
        self.path = Path(drive).expanduser().resolve()
        self.load_directory()

    def set_remote(self, conn: RemoteConnection) -> None:
        self.mode = "remote"
        self.remote_conn = conn
        self.remote_path = ""
        self.load_directory()

    def exit_remote(self) -> None:
        self.mode = "local"
        self.remote_conn = None
        self.remote_path = ""
        self.load_directory()

    @property
    def selected_entry(self) -> tuple[Path | str, str] | None:
        table = self.query_one(DataTable)
        if not self.entries:
            return None
        idx = table.cursor_row
        if idx is None or not (0 <= idx < len(self.entries)):
            return None
        return self.entries[idx]

    def go_up(self) -> None:
        if self.mode == "remote":
            self._remote_go_up()
        elif self.path.parent != self.path:
            self.path = self.path.parent
            self.load_directory()

    def _remote_go_up(self) -> None:
        if not self.remote_path:
            self.exit_remote()
            return
        self.remote_path = self.remote_path.rsplit("/", 1)[0] if "/" in self.remote_path else ""
        self.load_directory()

    # ----------------------------------------------------------------- events
    @on(DataTable.RowSelected)
    def _handle_enter(self, event: DataTable.RowSelected) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        identifier, kind = entry
        if self.mode == "remote":
            self._handle_remote_enter(identifier, kind)
            return
        path = identifier
        if kind in ("parent", "dir"):
            self.path = path.resolve()
            self.load_directory()
        elif kind == "file" and path.suffix.lower() in self.SUPPORTED_SUFFIXES:
            self.post_message(self.FileSelected(path))

    def _handle_remote_enter(self, name: str, kind: str) -> None:
        if kind == "parent":
            self._remote_go_up()
            return
        if kind == "dir":
            self.remote_path = f"{self.remote_path}/{name}" if self.remote_path else name
            self.load_directory()
            return
        if kind == "file" and Path(name).suffix.lower() in self.SUPPORTED_SUFFIXES:
            remote_key = f"{self.remote_path}/{name}" if self.remote_path else name
            self._download_and_open(remote_key, name)

    def _download_and_open(self, remote_key: str, name: str) -> None:
        conn = self.remote_conn
        tmp_dir = Path(tempfile.gettempdir()) / "pandas_commander_remote" / conn.name
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
            dest = tmp_dir / name
            remote_backends.download(conn, remote_key, dest)
        except Exception as exc:  # noqa: BLE001 - surface any backend/auth/network error
            self.app.notify(f"Download failed: {exc}", severity="error")
            return
        self.app.notify(f"Downloaded read-only copy of {name}")
        self.post_message(self.FileSelected(dest))

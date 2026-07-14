from __future__ import annotations

from pathlib import Path
from typing import Iterable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


class _DirOnlyTree(DirectoryTree):
    """A DirectoryTree that only lists directories (files are filtered out)."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [p for p in paths if self._safe_is_dir(p)]


class DirectoryPickerScreen(ModalScreen[Path | None]):
    """Popup directory browser used to pick a Copy/Move/Download destination.

    Dismisses with the chosen directory (a Path), or None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, start_path: Path, prompt: str = "Choose a destination directory:") -> None:
        super().__init__()
        self.start_path = start_path
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.prompt)
            yield Label(str(self.start_path), id="picker-path")
            yield _DirOnlyTree(self.start_path, id="picker-tree")
            with Horizontal(id="buttons"):
                yield Button("Choose directory", variant="primary", id="choose")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        tree = self.query_one(_DirOnlyTree)
        tree.cursor_line = 0
        tree.focus()

    @on(DirectoryTree.NodeHighlighted)
    def _highlighted(self, event: DirectoryTree.NodeHighlighted) -> None:
        if event.node.data is not None:
            self.query_one("#picker-path", Label).update(str(event.node.data.path))

    @on(Button.Pressed, "#choose")
    def _choose(self) -> None:
        tree = self.query_one(_DirOnlyTree)
        node = tree.cursor_node
        path = node.data.path if node is not None and node.data is not None else self.start_path
        self.dismiss(path)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

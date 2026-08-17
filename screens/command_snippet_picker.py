from __future__ import annotations

from panels.cli_snippets import CLI_SNIPPETS, OS_LABELS
from screens.filterable_picker import FilterablePickerScreen


class CommandSnippetPickerScreen(FilterablePickerScreen):
    """Filterable picker of curated data one-liners (Linux/macOS/PowerShell)
    for the shell command line. Enter inserts the chosen command."""

    def __init__(self, initial_filter: str = "") -> None:
        items = [
            (
                f"{OS_LABELS[os_tag]} {label} {command}",
                f"[{OS_LABELS[os_tag]}] {label} — {command}",
                command,
            )
            for os_tag, label, command in CLI_SNIPPETS
        ]
        super().__init__(
            "Data one-liners  (type to filter, Enter to insert, Esc to cancel)",
            items,
            placeholder="Filter one-liners…",
            initial_filter=initial_filter,
        )

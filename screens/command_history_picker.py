from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text

from panels.command_history import CommandHistory
from screens.filterable_picker import FilterablePickerScreen


def _relative_time(iso_ts: str) -> str:
    try:
        then = datetime.fromisoformat(iso_ts)
    except ValueError:
        return iso_ts
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - then).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


class CommandHistoryPickerScreen(FilterablePickerScreen):
    """Filterable, atuin-style picker over the sqlite command history:
    most-recently-run commands first, Enter fills the command line with the
    highlighted one (does not run it)."""

    def __init__(self, history: CommandHistory, initial_filter: str = "") -> None:
        rows = history.recent()
        items = []
        for command, last_ran, last_cwd, last_exit, runs in rows:
            if last_exit is None:
                mark = "?"
            elif last_exit != 0:
                mark = "✗"
            else:
                mark = " "
            display = Text(f"{mark} ", style="dim" if mark == " " else "bold red")
            display.append(command, style="bold" if mark != "✗" else "")
            display.append(f"   x{runs} · {_relative_time(last_ran)} · {last_cwd}", style="dim")
            items.append((f"{command} {last_cwd}", display, command))
        title = (
            "Command history  (type to filter, Enter to fill command line, Esc to cancel)"
            if items
            else "Command history — empty (run some commands first)"
        )
        super().__init__(title, items, placeholder="Filter history…", initial_filter=initial_filter)

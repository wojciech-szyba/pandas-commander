from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from panels import remote_sources


class DriveScreen(ModalScreen[tuple[str, str] | None]):
    """CHNG DRV popup: pick a local drive/mount or a configured remote connection.

    Dismisses with ("local", drive) or ("remote", connection_name), or None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self.local_drives = remote_sources.list_local_drives()
        self.connections = remote_sources.list_connections()

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Change drive")
            options: list[Option | None] = [Option("Local:", id="_hdr_local", disabled=True)]
            for drive in self.local_drives:
                options.append(Option(f"  {drive}", id=f"local:{drive}"))

            options.append(None)  # separator
            options.append(Option("Remote:", id="_hdr_remote", disabled=True))
            if self.connections:
                for conn in self.connections:
                    options.append(Option(f"  {conn.name}  [{conn.type}]", id=f"remote:{conn.name}"))
            else:
                options.append(
                    Option("  (none configured — see remote.ini)", id="_hdr_none", disabled=True)
                )
            yield OptionList(*options, id="drive-list")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id or ""
        if opt_id.startswith("_"):
            return
        kind, _, value = opt_id.partition(":")
        self.dismiss((kind, value))

    def action_cancel(self) -> None:
        self.dismiss(None)

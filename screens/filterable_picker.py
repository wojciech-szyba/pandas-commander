"""Reusable filter-box-over-OptionList modal, shared by the command
snippets picker and the command history picker."""
from __future__ import annotations

from typing import Any

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

# (search_text, display, value): `search_text` is matched against the filter
# query, `display` is what the option list shows (str or Rich renderable),
# `value` is what gets dismissed on selection.
PickerItem = tuple[str, Any, str]


class FilterInput(Input):
    """Input that drives a sibling OptionList's cursor on Up/Down/Enter,
    so the list can be filtered and navigated without moving focus."""

    def __init__(self, option_list: OptionList, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._option_list = option_list

    def on_key(self, event: events.Key) -> None:
        if event.key == "down":
            self._option_list.action_cursor_down()
            event.stop()
        elif event.key == "up":
            self._option_list.action_cursor_up()
            event.stop()
        elif event.key == "enter":
            if self._option_list.highlighted is None and self._option_list.option_count:
                self._option_list.highlighted = 0
            self._option_list.action_select()
            event.stop()


class FilterablePickerScreen(ModalScreen[str | None]):
    """Filter box + live-filtered OptionList. Enter dismisses with the
    highlighted item's value, Escape cancels with None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        items: list[PickerItem],
        placeholder: str = "Filter…",
        initial_filter: str = "",
    ) -> None:
        super().__init__()
        self.title_text = title
        self.items = items
        self.placeholder = placeholder
        self.initial_filter = initial_filter
        self._visible: list[PickerItem] = []

    def compose(self) -> ComposeResult:
        option_list = OptionList(id="filter-options")
        with Vertical(id="dialog"):
            yield Label(self.title_text)
            yield FilterInput(
                option_list,
                value=self.initial_filter,
                placeholder=self.placeholder,
                id="filter-input",
            )
            yield option_list

    def on_mount(self) -> None:
        self._refresh_options(self.initial_filter)
        filt = self.query_one("#filter-input", Input)
        filt.focus()
        filt.action_end()

    def _refresh_options(self, query: str) -> None:
        option_list = self.query_one("#filter-options", OptionList)
        option_list.clear_options()
        query = query.casefold()
        self._visible = (
            [item for item in self.items if query in item[0].casefold()]
            if query
            else list(self.items)
        )
        if self._visible:
            option_list.add_options(
                Option(display, id=str(i))
                for i, (_search, display, _value) in enumerate(self._visible)
            )
            option_list.highlighted = 0
        else:
            option_list.add_option(Option("(no matches)", disabled=True))

    @on(Input.Changed, "#filter-input")
    def _filter_changed(self, event: Input.Changed) -> None:
        self._refresh_options(event.value)

    @on(OptionList.OptionSelected, "#filter-options")
    def _option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        _search, _display, value = self._visible[int(event.option.id)]
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)

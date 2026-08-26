"""Tests for screens/directory_picker.py — DirectoryPickerScreen modal and
its dirs-only DirectoryTree filter."""
from __future__ import annotations

import pytest
from textual.widgets import DirectoryTree, Label
from textual.widgets._directory_tree import DirEntry

from screens.directory_picker import DirectoryPickerScreen, _DirOnlyTree


# ------------------------------------------------------------------- filtering

def test_dir_only_tree_filters_out_files(tmp_path):
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    tree = _DirOnlyTree(tmp_path)
    paths = list(tmp_path.iterdir())
    filtered = list(tree.filter_paths(paths))
    assert set(filtered) == {tmp_path / "a_dir", tmp_path / "b_dir"}


def test_dir_only_tree_empty_directory():
    tree = _DirOnlyTree(".")
    assert list(tree.filter_paths([])) == []


# ---------------------------------------------------------------------- screen

@pytest.mark.asyncio
async def test_directory_picker_shows_prompt_and_start_path(screen_harness, tmp_path):
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path, "Copy 'x' to:"))
    async with app.run_test():
        assert app.screen.query_one(Label).content == "Copy 'x' to:"
        assert app.screen.query_one("#picker-path", Label).content == str(tmp_path)


@pytest.mark.asyncio
async def test_directory_picker_focuses_tree(screen_harness, tmp_path):
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test():
        assert app.focused is app.screen.query_one(_DirOnlyTree)


@pytest.mark.asyncio
async def test_directory_picker_highlight_updates_path_label(screen_harness, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test():
        tree = app.screen.query_one(_DirOnlyTree)
        node = tree.root
        node.data = DirEntry(path=sub)
        event = DirectoryTree.NodeHighlighted(node)
        # Call the handler directly rather than relying on message-bubbling
        # timing; the unit under test is the handler's own logic.
        app.screen._highlighted(event)
        assert app.screen.query_one("#picker-path", Label).content == str(sub)


@pytest.mark.asyncio
async def test_directory_picker_choose_button_dismisses_with_cursor_path(screen_harness, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test() as pilot:
        tree = app.screen.query_one(_DirOnlyTree)
        tree.root.data = DirEntry(path=sub)
        tree.cursor_line = 0
        await pilot.click("#choose")
        await pilot.pause()
        assert app.result == sub


@pytest.mark.asyncio
async def test_directory_picker_choose_falls_back_to_start_path_without_cursor(screen_harness, tmp_path, monkeypatch):
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test() as pilot:
        tree = app.screen.query_one(_DirOnlyTree)
        monkeypatch.setattr(type(tree), "cursor_node", property(lambda self: None))
        await pilot.click("#choose")
        await pilot.pause()
        assert app.result == tmp_path


@pytest.mark.asyncio
async def test_directory_picker_cancel_button_dismisses_none(screen_harness, tmp_path):
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test() as pilot:
        await pilot.click("#cancel")
        await pilot.pause()
        assert app.result is None


@pytest.mark.asyncio
async def test_directory_picker_escape_dismisses_none(screen_harness, tmp_path):
    app = screen_harness(lambda: DirectoryPickerScreen(tmp_path))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


@pytest.mark.asyncio
async def test_directory_picker_default_prompt():
    from screens.directory_picker import DirectoryPickerScreen as DPS

    screen = DPS.__new__(DPS)  # inspect the default without mounting
    import inspect

    default_prompt = inspect.signature(DPS.__init__).parameters["prompt"].default
    assert default_prompt == "Choose a destination directory:"

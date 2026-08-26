"""Widget-level tests for panels/EditorPanel.py, driven through Textual's
Pilot test harness (a minimal host App mounts the PandasEditorPanel under
test, exactly as pandas-commander.py itself does)."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, TextArea

from panels.EditorPanel import EditorPanel, PandasEditorPanel, _DataFrameTextArea


class _Harness(App):
    """Minimal host app so EditorPanel can be mounted/queried in isolation."""

    def __init__(self):
        super().__init__()
        self.notifications: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield PandasEditorPanel()

    def notify(self, message, *, severity="information", **kwargs):
        self.notifications.append((str(message), severity))
        return super().notify(message, severity=severity, **kwargs)


def _area(app: App) -> TextArea:
    return app.query_one("#ep-area", TextArea)


def _panel(app: App) -> EditorPanel:
    return app.query_one(EditorPanel)


# --------------------------------------------------------------------- load_file

@pytest.mark.asyncio
async def test_load_text_file_shows_content_and_hides_placeholder(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello world", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        assert area.text == "hello world"
        assert area.display is True
        assert app.query_one("#ep-placeholder", Static).display is False
        assert area.language is None


@pytest.mark.asyncio
async def test_load_python_file_sets_python_language(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("print(1)\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert _area(app).language == "python"


@pytest.mark.asyncio
async def test_load_sql_file_sets_sql_language(tmp_path):
    path = tmp_path / "query.sql"
    path.write_text("select 1;", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert _area(app).language == "sql"


@pytest.mark.asyncio
async def test_load_binary_file_shows_dataframe_preview(tmp_path):
    path = tmp_path / "data.pkl"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_pickle(path)
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        text = _area(app).text
        assert "a" in text and "b" in text
        assert "1" in text


@pytest.mark.asyncio
async def test_load_binary_file_missing_dependency_shows_install_hint(tmp_path):
    path = tmp_path / "data.parquet"
    path.write_bytes(b"not really parquet, pyarrow unavailable anyway")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        text = _area(app).text
        assert "missing dependency" in text
        assert "pip install pandas pyarrow" in text


@pytest.mark.asyncio
async def test_load_unreadable_file_shows_error_placeholder(tmp_path):
    path = tmp_path / "ghost.py"  # never created
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        placeholder = app.query_one("#ep-placeholder", Static)
        assert placeholder.display is True
        assert "Cannot read file" in placeholder.content
        assert _area(app).display is False


@pytest.mark.asyncio
async def test_load_runnable_suffix_shows_results_panel(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert app.query_one("#ep-result-header", Static).display is True
        assert app.query_one("#ep-result-table", DataTable).display is True


@pytest.mark.asyncio
async def test_load_non_runnable_suffix_hides_results_panel(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hi", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert app.query_one("#ep-result-header", Static).display is False
        assert app.query_one("#ep-result-table", DataTable).display is False


# ------------------------------------------------------------------- check_action

@pytest.mark.asyncio
async def test_check_action_none_without_loaded_file():
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        assert panel.check_action("run", ()) is None


@pytest.mark.asyncio
async def test_check_action_true_for_runnable_suffix(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_action("run", ()) is True
        assert panel.check_action("cmd_pandas", ()) is True


@pytest.mark.asyncio
async def test_check_action_none_for_non_runnable_suffix(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hi", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_action("run", ()) is None


# ------------------------------------------------------------------------ action_save

@pytest.mark.asyncio
async def test_action_save_writes_text_and_notifies(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("old\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        _area(app).text = "new content\n"
        panel.action_save()
        assert path.read_text(encoding="utf-8") == "new content\n"
        assert any("Saved" in msg for msg, _sev in app.notifications)


@pytest.mark.asyncio
async def test_action_save_binary_file_warns_and_does_not_write(tmp_path):
    path = tmp_path / "data.pkl"
    pd.DataFrame({"a": [1]}).to_pickle(path)
    original_bytes = path.read_bytes()
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_save()
        assert path.read_bytes() == original_bytes
        assert any(sev == "warning" for _msg, sev in app.notifications)


@pytest.mark.asyncio
async def test_action_save_no_file_loaded_is_noop():
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.action_save()  # must not raise
        assert app.notifications == []


@pytest.mark.asyncio
async def test_action_save_oserror_notifies_error(tmp_path, monkeypatch):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)

        def boom(self, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", boom)
        panel.action_save()
        assert any(sev == "error" and "Save failed" in msg for msg, sev in app.notifications)


@pytest.mark.asyncio
async def test_save_discards_autosave_sidecar(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    sidecar = tmp_path / ".script.py.autosave"
    sidecar.write_text("stale backup", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_save()
        assert not sidecar.exists()


# -------------------------------------------------------------------------- run

@pytest.mark.asyncio
async def test_action_run_renders_dataframe_result(tmp_path):
    path = tmp_path / "script.pandas"
    path.write_text("import pandas as pd\ndf = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["a", "b"]
        assert table.row_count == 2
        header_text = app.query_one("#ep-result-header", Static).content
        assert "2 rows" in header_text


@pytest.mark.asyncio
async def test_action_run_shows_traceback_on_error(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("raise ValueError('boom')\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        rendered = "\n".join(str(table.get_cell_at((r, 0))) for r in range(table.row_count))
        assert "ValueError" in rendered
        assert "boom" in rendered
        header_text = app.query_one("#ep-result-header", Static).content
        assert "error" in header_text


@pytest.mark.asyncio
async def test_action_run_shows_stdout_when_no_dataframe(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("print('hello from script')\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert str(table.get_cell_at((0, 0))) == "hello from script"


@pytest.mark.asyncio
async def test_action_run_no_output_placeholder(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert str(table.get_cell_at((0, 0))) == "(no output)"


@pytest.mark.asyncio
async def test_action_run_noop_without_loaded_file():
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.action_run()  # must not raise


# ---------------------------------------------------------------------- run (SQL)

@pytest.mark.asyncio
async def test_run_sql_no_config_shows_warning(tmp_path, chdir_tmp):
    # chdir_tmp keeps sql_tools' cwd-fallback lookup from finding this
    # repository's own real db_connections.ini.
    path = tmp_path / "query.sql"
    path.write_text("select 1;", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        header_text = app.query_one("#ep-result-header", Static).content
        assert "not configured" in header_text
        assert any(sev == "warning" for _msg, sev in app.notifications)


@pytest.mark.asyncio
async def test_run_sql_executes_against_sqlite(tmp_path):
    path = tmp_path / "query.sql"
    (tmp_path / "db_connections.ini").write_text(
        f"[default]\nurl = sqlite:///{tmp_path / 'app.db'}\n", encoding="utf-8"
    )
    path.write_text(
        "create table t (id integer, name text);"
        "insert into t values (1, 'a'), (2, 'b');"
        "select id, name from t order by id;",
        encoding="utf-8",
    )
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["id", "name"]
        assert table.row_count == 2
        header_text = app.query_one("#ep-result-header", Static).content
        assert "2 rows" in header_text


@pytest.mark.asyncio
async def test_run_sql_runs_only_selected_text(tmp_path):
    path = tmp_path / "query.sql"
    (tmp_path / "db_connections.ini").write_text(
        f"[default]\nurl = sqlite:///{tmp_path / 'app2.db'}\n", encoding="utf-8"
    )
    full_sql = "create table t (id integer);insert into t values (1);select id from t;"
    path.write_text(full_sql, encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        # Select only "select id from t" so the create/insert never run --
        # which must surface as a "no such table" error.
        select_start = full_sql.index("select id from t")
        start_loc = area.document.get_location_from_index(select_start)
        end_loc = area.document.get_location_from_index(len(full_sql) - 1)
        area.selection = area.selection.__class__(start_loc, end_loc)
        panel.action_run()
        header_text = app.query_one("#ep-result-header", Static).content
        assert "error" in header_text


@pytest.mark.asyncio
async def test_run_sql_run_sql_import_error_shows_install_hint(tmp_path, monkeypatch):
    """Distinct from resolve_connection_url raising ImportError: this covers
    sql_tools.run_sql() itself (e.g. SQLAlchemy present but incomplete)
    raising ImportError."""
    path = tmp_path / "query.sql"
    (tmp_path / "db_connections.ini").write_text(
        f"[default]\nurl = sqlite:///{tmp_path / 'x.db'}\n", encoding="utf-8"
    )
    path.write_text("select 1;", encoding="utf-8")
    from panels import sql_tools

    def raise_import_error(*args, **kwargs):
        raise ImportError("no sqlalchemy")

    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        monkeypatch.setattr(sql_tools, "run_sql", raise_import_error)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        text = "\n".join(str(table.get_cell_at((r, 0))) for r in range(table.row_count))
        assert "SQLAlchemy is not installed" in text


@pytest.mark.asyncio
async def test_run_sql_import_error_shows_install_hint(tmp_path, monkeypatch):
    path = tmp_path / "query.sql"
    path.write_text("select 1;", encoding="utf-8")
    from panels import sql_tools

    def raise_import_error(*args, **kwargs):
        raise ImportError("no sqlalchemy")

    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        monkeypatch.setattr(sql_tools, "resolve_connection_url", raise_import_error)
        panel.action_run()
        text = "\n".join(
            str(app.query_one("#ep-result-table", DataTable).get_cell_at((r, 0)))
            for r in range(app.query_one("#ep-result-table", DataTable).row_count)
        )
        assert "SQLAlchemy is not installed" in text


# --------------------------------------------------------------------- autosave

@pytest.mark.asyncio
async def test_autosave_writes_sidecar_when_dirty(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        _area(app).text = "x = 2\n"
        panel._autosave()
        sidecar = path.with_name(".script.py.autosave")
        assert sidecar.read_text(encoding="utf-8") == "x = 2\n"


@pytest.mark.asyncio
async def test_autosave_skips_when_unchanged(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel._autosave()
        sidecar = path.with_name(".script.py.autosave")
        assert not sidecar.exists()


@pytest.mark.asyncio
async def test_autosave_skips_binary_files(tmp_path):
    path = tmp_path / "data.pkl"
    pd.DataFrame({"a": [1]}).to_pickle(path)
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel._autosave()
        sidecar = path.with_name(".data.pkl.autosave")
        assert not sidecar.exists()


@pytest.mark.asyncio
async def test_check_autosave_recovery_returns_none_when_no_sidecar(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_autosave_recovery() is None


@pytest.mark.asyncio
async def test_check_autosave_recovery_returns_text_when_sidecar_newer(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    sidecar = path.with_name(".script.py.autosave")
    sidecar.write_text("recovered text", encoding="utf-8")
    # Ensure the sidecar's mtime is strictly newer than the real file's.
    future = time.time() + 5
    import os

    os.utime(sidecar, (future, future))
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_autosave_recovery() == "recovered text"


@pytest.mark.asyncio
async def test_check_autosave_recovery_ignores_older_sidecar(tmp_path):
    path = tmp_path / "script.py"
    sidecar = path.with_name(".script.py.autosave")
    sidecar.write_text("old backup", encoding="utf-8")
    past = time.time() - 5
    import os

    os.utime(sidecar, (past, past))
    path.write_text("x = 1\n", encoding="utf-8")  # written after the sidecar
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_autosave_recovery() is None


@pytest.mark.asyncio
async def test_apply_recovered_text_loads_into_area(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.apply_recovered_text("recovered = True\n")
        assert _area(app).text == "recovered = True\n"


@pytest.mark.asyncio
async def test_discard_autosave_removes_sidecar(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    sidecar = path.with_name(".script.py.autosave")
    sidecar.write_text("stale", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.discard_autosave()
        assert not sidecar.exists()


@pytest.mark.asyncio
async def test_discard_autosave_missing_file_is_noop(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.discard_autosave()  # no sidecar present -- must not raise


# --------------------------------------------------------------- snippet insertion

@pytest.mark.asyncio
async def test_ensure_import_adds_missing_import():
    class FakeArea:
        def __init__(self, text):
            self.text = text
            self.inserted = None

        def insert(self, text, pos):
            self.inserted = (text, pos)

    area = FakeArea("df.head()\n")
    EditorPanel._ensure_import(area, "pandas")
    assert area.inserted == ("import pandas as pd\n\n", (0, 0))


@pytest.mark.asyncio
async def test_ensure_import_skips_when_already_present():
    class FakeArea:
        def __init__(self, text):
            self.text = text
            self.inserted = None

        def insert(self, text, pos):
            self.inserted = (text, pos)

    area = FakeArea("import pandas as pd\ndf.head()\n")
    EditorPanel._ensure_import(area, "pandas")
    assert area.inserted is None


@pytest.mark.asyncio
async def test_ensure_import_noop_for_dbt():
    class FakeArea:
        def __init__(self, text):
            self.text = text
            self.inserted = None

        def insert(self, text, pos):
            self.inserted = (text, pos)

    area = FakeArea("select 1")
    EditorPanel._ensure_import(area, "dbt")
    assert area.inserted is None


@pytest.mark.asyncio
async def test_cmd_pandas_pushes_snippet_picker_and_inserts_code(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("", encoding="utf-8")
    app = _Harness()
    async with app.run_test() as pilot:
        panel = _panel(app)
        panel.load_file(path)
        _area(app).focus()
        await pilot.press("ctrl+g")
        await pilot.pause()
        from screens.snippet_picker import SnippetPickerScreen

        assert isinstance(app.screen, SnippetPickerScreen)
        await pilot.press("enter")  # accept the first (highlighted) snippet
        await pilot.pause()
        text = _area(app).text
        assert "import pandas as pd" in text
        assert "read_csv" in text or "df" in text


# ---------------------------------------------------------- ghost-text suggestion

@pytest.mark.asyncio
async def test_update_suggestion_python_dot_completion(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("import pandas as pd\npd.read_c", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        area.move_cursor(area.document.end)
        area.update_suggestion()
        assert area.suggestion == "sv("


@pytest.mark.asyncio
async def test_update_suggestion_sql_keyword_completion(tmp_path):
    path = tmp_path / "query.sql"
    path.write_text("sel", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        area.move_cursor(area.document.end)
        area.update_suggestion()
        assert area.suggestion == "ect"


@pytest.mark.asyncio
async def test_update_suggestion_blank_for_unsupported_suffix(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("pd.read_c", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        area.move_cursor(area.document.end)
        area.update_suggestion()
        assert area.suggestion == ""


# -------------------------------------------------------------- right-click paste

@pytest.mark.asyncio
async def test_right_click_pastes_system_clipboard_at_cursor(tmp_path, monkeypatch):
    from textual import events

    path = tmp_path / "script.py"
    path.write_text("abc\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        assert isinstance(area, _DataFrameTextArea)
        monkeypatch.setattr("pyperclip.paste", lambda: "PASTED")

        event = events.MouseDown(
            widget=area, x=1, y=0, delta_x=0, delta_y=0, button=3,
            shift=False, meta=False, ctrl=False,
        )
        await area._on_mouse_down(event)
        assert "PASTED" in area.text


@pytest.mark.asyncio
async def test_right_click_no_clipboard_content_is_noop(tmp_path, monkeypatch):
    from textual import events

    path = tmp_path / "script.py"
    path.write_text("abc\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        monkeypatch.setattr("pyperclip.paste", lambda: "")

        event = events.MouseDown(
            widget=area, x=1, y=0, delta_x=0, delta_y=0, button=3,
            shift=False, meta=False, ctrl=False,
        )
        await area._on_mouse_down(event)
        assert area.text == "abc\n"


@pytest.mark.asyncio
async def test_update_suggestion_blank_when_text_selected(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("pd.read_c", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        area.selection = area.selection.__class__((0, 0), (0, 3))
        area.update_suggestion()
        assert area.suggestion == ""


@pytest.mark.asyncio
async def test_right_click_pyperclip_exception_leaves_text_unchanged(tmp_path, monkeypatch):
    import pyperclip
    from textual import events

    path = tmp_path / "script.py"
    path.write_text("abc\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)

        def boom():
            raise pyperclip.PyperclipException("no clipboard mechanism")

        monkeypatch.setattr(pyperclip, "paste", boom)
        event = events.MouseDown(
            widget=area, x=1, y=0, delta_x=0, delta_y=0, button=3,
            shift=False, meta=False, ctrl=False,
        )
        await area._on_mouse_down(event)  # must not raise
        assert area.text == "abc\n"


@pytest.mark.asyncio
async def test_left_click_falls_through_to_default_handling(tmp_path):
    from textual import events

    path = tmp_path / "script.py"
    path.write_text("abc\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        area = _area(app)
        event = events.MouseDown(
            widget=area, x=1, y=0, delta_x=0, delta_y=0, button=1,
            shift=False, meta=False, ctrl=False,
        )
        await area._on_mouse_down(event)  # delegates to TextArea's own handling
        assert area.text == "abc\n"  # left-click doesn't paste


# ------------------------------------------------------------ other snippet cmds

@pytest.mark.asyncio
async def test_cmd_polars_pushes_snippet_picker(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("", encoding="utf-8")
    app = _Harness()
    async with app.run_test() as pilot:
        panel = _panel(app)
        panel.load_file(path)
        _area(app).focus()
        await pilot.press("ctrl+o")
        await pilot.pause()
        from screens.snippet_picker import SnippetPickerScreen

        assert isinstance(app.screen, SnippetPickerScreen)
        assert app.screen.title_text == "Polars snippets"


@pytest.mark.asyncio
async def test_cmd_pyspark_pushes_snippet_picker(tmp_path):
    path = tmp_path / "script.py"
    path.write_text("", encoding="utf-8")
    app = _Harness()
    async with app.run_test() as pilot:
        panel = _panel(app)
        panel.load_file(path)
        _area(app).focus()
        await pilot.press("ctrl+t")
        await pilot.pause()
        from screens.snippet_picker import SnippetPickerScreen

        assert isinstance(app.screen, SnippetPickerScreen)
        assert app.screen.title_text == "PySpark snippets"


@pytest.mark.asyncio
async def test_cmd_dbt_pushes_snippet_picker(tmp_path):
    path = tmp_path / "query.sql"
    path.write_text("", encoding="utf-8")
    app = _Harness()
    async with app.run_test() as pilot:
        panel = _panel(app)
        panel.load_file(path)
        _area(app).focus()
        await pilot.press("ctrl+b")
        await pilot.pause()
        from screens.snippet_picker import SnippetPickerScreen

        assert isinstance(app.screen, SnippetPickerScreen)
        assert app.screen.title_text == "dbt snippets"


# --------------------------------------------------------------- action_run edges

@pytest.mark.asyncio
async def test_action_run_pandas_unavailable_falls_back_to_text_output(tmp_path, monkeypatch):
    """Simulates pandas being unimportable at the point action_run() tries to
    render a DataFrame result -- the ImportError is swallowed and the run
    falls back to plain text/traceback output."""
    import sys

    path = tmp_path / "script.py"
    path.write_text("print('fallback path')\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        monkeypatch.setitem(sys.modules, "pandas", None)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert str(table.get_cell_at((0, 0))) == "fallback path"


# ------------------------------------------------------------- _run_sql (DDL-only)

@pytest.mark.asyncio
async def test_run_sql_ddl_only_shows_summary_row(tmp_path):
    path = tmp_path / "query.sql"
    (tmp_path / "db_connections.ini").write_text(
        f"[default]\nurl = sqlite:///{tmp_path / 'ddl.db'}\n", encoding="utf-8"
    )
    path.write_text("create table t (id integer);insert into t values (1);", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        panel.action_run()
        table = app.query_one("#ep-result-table", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["output"]
        assert "statement(s) executed" in str(table.get_cell_at((0, 0)))


# ---------------------------------------------------------------------- autosave

@pytest.mark.asyncio
async def test_autosave_skips_when_area_not_displayed(tmp_path):
    path = tmp_path / "ghost.py"  # fails to load -> area.display becomes False
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert _area(app).display is False
        panel._autosave()  # must not raise despite current_path being set
        sidecar = path.with_name(".ghost.py.autosave")
        assert not sidecar.exists()


@pytest.mark.asyncio
async def test_autosave_oserror_is_swallowed(tmp_path, monkeypatch):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        _area(app).text = "x = 2\n"

        def boom(self, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", boom)
        panel._autosave()  # must not raise


@pytest.mark.asyncio
async def test_check_autosave_recovery_binary_file_returns_none_without_touching_disk(tmp_path):
    path = tmp_path / "data.pkl"
    pd.DataFrame({"a": [1]}).to_pickle(path)
    sidecar = path.with_name(".data.pkl.autosave")
    sidecar.write_text("should be ignored", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)
        assert panel.check_autosave_recovery() is None


@pytest.mark.asyncio
async def test_check_autosave_recovery_oserror_returns_none(tmp_path, monkeypatch):
    path = tmp_path / "script.py"
    path.write_text("x = 1\n", encoding="utf-8")
    sidecar = path.with_name(".script.py.autosave")
    sidecar.write_text("recovered", encoding="utf-8")
    app = _Harness()
    async with app.run_test():
        panel = _panel(app)
        panel.load_file(path)

        def boom(self, *args, **kwargs):
            raise OSError("stat failed")

        monkeypatch.setattr(Path, "stat", boom)
        assert panel.check_autosave_recovery() is None

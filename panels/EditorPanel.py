from __future__ import annotations

import contextlib
import io
import traceback
from pathlib import Path

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import (
    DataTable,
    Static,
    TextArea,
)


class _DataFrameTextArea(TextArea):
    """TextArea that yields ctrl+c to the panel's Concat binding for .pandas/.polars files."""

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "copy":
            editor = self.parent
            if getattr(editor, "_dataframe_flavour", lambda: None)():
                # Disable copy so ctrl+c bubbles up to EditorPanel's Concat.
                return None
        return super().check_action(action, parameters)


# ---------------------------------------------------------------- EditorPanel
class EditorPanel(Vertical):
    """Right pane: inline viewer/editor for .py, .csv, and .parquet files."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "run", "Run"),
        Binding("ctrl+g", "group_by", "GroupBy"),
        Binding("ctrl+u", "unique", "Unique"),
        Binding("ctrl+m", "merge", "Merge"),
        Binding("ctrl+c", "concat", "Concat"),
        Binding("ctrl+p", "profiling", "Profiling"),
        Binding("ctrl+w", "write_df_as", "WriteToFile"),
    ]

    # Snippets inserted at the cursor, keyed by dataframe flavour.
    SNIPPETS = {
        ".pandas": {
            "group_by": 'df.groupby("column").agg({"value": "sum"})',
            "unique": 'df["column"].unique()',
            "merge": 'pd.merge(left, right, on="key", how="inner")',
            "concat": 'pd.concat([df1, df2], axis=0)',
            "write_df_as": 'df.to_csv("filename", compression="gzip")',
            "profiling": """
            summary = pd.DataFrame({
                "dtype": df.dtypes,
                "non_null": df.count(),
                "missing": df.isna().sum(),
                "missing_%": df.isna().mean().mul(100).round(1),
                "unique": df.nunique(),
                })
            print(summary)
            print(df.describe(include="all").T)
            """
    },
        ".polars": {
            "group_by": 'df.group_by("column").agg(pl.col("value").sum())',
            "unique": 'df.select(pl.col("column").unique())',
            "merge": 'left.join(right, on="key", how="inner")',
            "concat": 'pl.concat([df1, df2])',
            "write_df_as": 'df.to_csv("filename", compression="gzip")',
        },
    }

    _RUNNABLE_SUFFIXES = {".py", ".pandas", ".polars"}

    # How often the open file is auto-backed-up, in seconds.
    AUTOSAVE_INTERVAL = 60

    def __init__(self) -> None:
        super().__init__(id="right")
        self.current_path: Path | None = None
        # Content currently persisted in the real file (set on load / manual save).
        self._last_saved_text: str = ""
        # Content last written to the .autosave sidecar (avoids rewriting it unchanged).
        self._last_autosaved_text: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="ep-header")
        yield Static(
            "Select a  .py  .csv  or  .parquet  file in the left panel.",
            id="ep-placeholder",
        )
        yield _DataFrameTextArea("", id="ep-area")
        yield Static("Results", id="ep-result-header")
        yield DataTable(id="ep-result-table", show_cursor=True, zebra_stripes=True)

    def on_mount(self) -> None:
        self.query_one("#ep-area", TextArea).display = False
        self.query_one("#ep-result-header", Static).display = False
        self.query_one("#ep-result-table", DataTable).display = False
        self.set_interval(self.AUTOSAVE_INTERVAL, self._autosave)

    # ----------------------------------------------------------------- public
    def load_file(self, path: Path) -> None:
        self.current_path = path
        header = self.query_one("#ep-header", Static)
        header.update(Text(f" {path} ", overflow="ellipsis", no_wrap=True))

        placeholder = self.query_one("#ep-placeholder", Static)
        area = self.query_one("#ep-area", TextArea)
        result_header = self.query_one("#ep-result-header", Static)
        result_table = self.query_one("#ep-result-table", DataTable)

        try:
            suffix = path.suffix.lower()
            if suffix == ".parquet":
                content = self._parquet_to_text(path)
            else:
                content = path.read_text(encoding="utf-8", errors="replace")

            area.language = "python" if suffix in [".py", ".pandas", ".polars"] else None
            area.load_text(content)
            # Freshly loaded content == what is on disk; nothing to auto-back-up yet.
            self._last_saved_text = content
            self._last_autosaved_text = content
            placeholder.display = False
            area.display = True
            area.focus()

            is_runnable = suffix in self._RUNNABLE_SUFFIXES
            result_header.display = is_runnable
            result_table.display = is_runnable
            if is_runnable:
                result_table.clear(columns=True)
        except Exception as exc:  # noqa: BLE001
            placeholder.update(f"Cannot read file: {exc}")
            placeholder.display = True
            area.display = False
            result_header.display = False
            result_table.display = False
        finally:
            # Show/hide the pandas/polars bindings for the freshly loaded file.
            self.refresh_bindings()

    # ------------------------------------------------------- conditional binds
    def _dataframe_flavour(self) -> str | None:
        """Return the snippet key (.pandas/.polars) for the open file, else None."""
        if self.current_path is None:
            return None
        suffix = self.current_path.suffix.lower()
        return suffix if suffix in self.SNIPPETS else None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("group_by", "unique", "merge", "concat", "profiling", "write_df_as"):
            # True when applicable, None to hide the binding from the footer.
            return True if self._dataframe_flavour() else None
        if action == "run":
            if self.current_path is None:
                return None
            return True if self.current_path.suffix.lower() in self._RUNNABLE_SUFFIXES else None
        return True

    def _insert_snippet(self, action: str) -> None:
        flavour = self._dataframe_flavour()
        if flavour is None:
            return
        snippet = self.SNIPPETS[flavour][action]
        self.query_one("#ep-area", TextArea).insert(snippet)

    def action_group_by(self) -> None:
        self._insert_snippet("group_by")

    def action_unique(self) -> None:
        self._insert_snippet("unique")

    def action_merge(self) -> None:
        self._insert_snippet("merge")

    def action_concat(self) -> None:
        self._insert_snippet("concat")

    def action_write_df_as(self) -> None:
        self._insert_snippet("write_df_as")

    def action_profiling(self) -> None:
        self._insert_snippet("profiling")

    # ------------------------------------------------------------------ action
    def action_run(self) -> None:
        if self.current_path is None:
            return

        code = self.query_one("#ep-area", TextArea).text
        result_table = self.query_one("#ep-result-table", DataTable)
        result_header = self.query_one("#ep-result-header", Static)
        result_table.clear(columns=True)

        namespace: dict = {}
        captured = io.StringIO()
        error: str | None = None

        try:
            with contextlib.redirect_stdout(captured):
                exec(compile(code, str(self.current_path), "exec"), namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()

        output = captured.getvalue()

        # Try to render a pandas DataFrame from the `df` variable.
        df = namespace.get("df")
        try:
            import pandas as pd  # noqa: PLC0415

            if isinstance(df, pd.DataFrame):
                cols = [str(c) for c in df.columns]
                result_table.add_columns(*cols)
                for row in df.itertuples(index=False, name=None):
                    result_table.add_row(*[str(v) for v in row])
                result_header.update(f"Results  ({len(df)} rows × {len(cols)} cols)")
                return
        except ImportError:
            pass

        # Fall back: show text output or traceback line-by-line.
        text = error if error else (output if output else "(no output)")
        result_table.add_column("output")
        for line in text.splitlines():
            result_table.add_row(line)
        result_header.update("Results" + (" — error" if error else ""))

    # ----------------------------------------------------------------- action
    def action_save(self) -> None:
        if self.current_path is None:
            return
        if self.current_path.suffix.lower() == ".parquet":
            self.app.notify("Parquet files cannot be saved from the text editor.", severity="warning")
            return
        text = self.query_one("#ep-area", TextArea).text
        try:
            self.current_path.write_text(text, encoding="utf-8")
            self._last_saved_text = text
            self._last_autosaved_text = text
            self._discard_autosave(self.current_path)
            self.app.notify(f"Saved {self.current_path.name}")
        except OSError as exc:
            self.app.notify(f"Save failed: {exc}", severity="error")

    # --------------------------------------------------------------- autosave
    @staticmethod
    def _autosave_path(path: Path) -> Path:
        """Sidecar backup file for `path` (e.g. foo.pandas -> .foo.pandas.autosave)."""
        return path.with_name(f".{path.name}.autosave")

    def _is_editable(self, path: Path | None) -> bool:
        """Parquet is a read-only preview, so it is never auto-backed-up."""
        return path is not None and path.suffix.lower() != ".parquet"

    def _autosave(self) -> None:
        """Periodically mirror unsaved edits to the sidecar so nothing is lost."""
        if not self._is_editable(self.current_path):
            return
        area = self.query_one("#ep-area", TextArea)
        if not area.display:
            return
        text = area.text
        # Only write when there are unsaved changes that the sidecar doesn't have yet.
        if text == self._last_saved_text or text == self._last_autosaved_text:
            return
        try:
            self._autosave_path(self.current_path).write_text(text, encoding="utf-8")
            self._last_autosaved_text = text
        except OSError:
            pass

    def _discard_autosave(self, path: Path) -> None:
        swap = self._autosave_path(path)
        try:
            swap.unlink()
        except OSError:
            pass

    def check_autosave_recovery(self) -> str | None:
        """Return recovered text if a sidecar newer than the current file exists."""
        if not self._is_editable(self.current_path):
            return None
        swap = self._autosave_path(self.current_path)
        try:
            if swap.exists() and swap.stat().st_mtime > self.current_path.stat().st_mtime:
                return swap.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        return None

    def apply_recovered_text(self, text: str) -> None:
        """Load recovered content into the editor (still unsaved vs. the real file)."""
        self.query_one("#ep-area", TextArea).load_text(text)
        self._last_autosaved_text = text

    def discard_autosave(self) -> None:
        if self.current_path is not None:
            self._discard_autosave(self.current_path)

    # ----------------------------------------------------------------- helper
    @staticmethod
    def _parquet_to_text(path: Path) -> str:
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(path)
            return df.to_string()
        except ImportError:
            return (
                "[pandas is not installed — cannot preview .parquet files]\n\n"
                "Install with:  pip install pandas"
            )

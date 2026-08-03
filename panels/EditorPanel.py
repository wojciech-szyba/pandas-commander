from __future__ import annotations

import contextlib
import io
import re
import traceback
from pathlib import Path

import pyperclip
from rich.text import Text

from panels import formats, snippets, sql_tools
from screens.snippet_picker import SnippetPickerScreen

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import (
    DataTable,
    Static,
    TextArea,
)
from textual.widgets.text_area import Selection

# ------------------------------------------------------------- python autocomplete
# Ghost-text (inline) completion for .py/.pandas/.polars files, in priority
# order — the first candidate that starts with the typed prefix wins. Accepted
# with the right-arrow key, same as TextArea's built-in suggestion mechanism.
# Dispatch is alias-driven (pd/pl/spark/F...) so pandas, Polars and PySpark
# code can all be completed in the same file.
_PANDAS_TOP_LEVEL = [
    "DataFrame(", "Series(", "read_csv(", "read_excel(", "read_parquet(",
    "read_json(", "read_sql(", "read_html(", "read_pickle(", "read_feather(",
    "read_orc(", "read_xml(", "read_hdf(", "read_stata(", "read_sas(",
    "read_spss(", "read_clipboard(", "read_table(", "concat(", "merge(",
    "merge_asof(",
    "merge_ordered(", "pivot_table(", "crosstab(", "cut(", "qcut(",
    "to_datetime(", "to_numeric(", "to_timedelta(", "date_range(", "isna(",
    "isnull(", "notna(", "notnull(", "get_dummies(", "melt(", "unique(",
    "value_counts(", "set_option(", "get_option(", "reset_option(",
    "Categorical(", "Index(", "MultiIndex(", "Timestamp(", "Timedelta(",
    "options", "NaT", "NA", "array(",
]

_DATAFRAME_METHODS = [
    "head(", "tail(", "info(", "describe(", "shape", "columns", "index",
    "dtypes", "values", "copy(", "groupby(", "merge(", "join(",
    "pivot_table(", "pivot(", "melt(", "sort_values(", "sort_index(",
    "reset_index(", "set_index(", "drop(", "drop_duplicates(", "dropna(",
    "fillna(", "replace(", "rename(", "astype(", "apply(", "applymap(",
    "map(", "filter(", "query(", "loc[", "iloc[", "at[", "iat[", "isna(",
    "isnull(", "notna(", "notnull(", "unique(", "nunique(", "value_counts(",
    "sample(", "nlargest(", "nsmallest(", "to_csv(", "to_excel(",
    "to_parquet(", "to_json(", "to_dict(", "to_numpy(", "to_string(",
    "to_list(", "corr(", "cov(", "mean(", "median(", "mode(", "sum(",
    "min(", "max(", "std(", "var(", "count(", "cumsum(", "cumprod(",
    "cummax(", "cummin(", "diff(", "pct_change(", "rolling(", "expanding(",
    "resample(", "shift(", "clip(", "round(", "abs(", "agg(", "aggregate(",
    "transform(", "pipe(", "assign(", "explode(", "stack(", "unstack(", "T",
]

# Identifiers whose attributes are clearly not dataframes, so `.` after them
# should not offer DataFrame/Series methods.
_NON_DATAFRAME_NAMES = {
    "os", "sys", "re", "np", "numpy", "json", "math", "io", "shutil",
    "subprocess", "pathlib", "Path", "datetime", "time", "self", "logging",
}

_PANDAS_ALIASES = {"pd", "pandas"}

_POLARS_TOP_LEVEL = [
    "DataFrame(", "Series(", "LazyFrame(", "read_csv(", "read_parquet(",
    "read_json(", "read_ndjson(", "read_excel(", "read_ipc(", "read_avro(",
    "read_database(", "scan_csv(", "scan_parquet(", "scan_ndjson(",
    "scan_ipc(", "concat(", "col(", "cols(", "lit(", "when(", "all(", "any(",
    "sum(", "min(", "max(", "mean(", "median(", "count(", "first(", "last(",
    "struct(", "from_pandas(", "from_numpy(", "from_dict(", "from_records(",
    "date_range(", "datetime(", "duration(", "concat_str(", "concat_list(",
    "Config", "Int8", "Int16", "Int32", "Int64", "Float32", "Float64",
    "Utf8", "Boolean", "Date", "Datetime", "Duration", "List", "Struct",
]

_POLARS_DF_METHODS = [
    "head(", "tail(", "glimpse(", "describe(", "shape", "columns", "dtypes",
    "schema", "height", "width", "select(", "with_columns(", "filter(",
    "group_by(", "agg(", "sort(", "join(", "join_asof(", "unique(", "drop(",
    "drop_nulls(", "fill_null(", "fill_nan(", "rename(", "explode(",
    "melt(", "unpivot(", "pivot(", "to_dummies(", "sample(", "slice(",
    "limit(", "top_k(", "bottom_k(", "null_count(", "n_unique(",
    "is_duplicated(", "is_unique(", "with_row_index(", "lazy(", "collect(",
    "sink_parquet(", "sink_csv(", "to_pandas(", "to_numpy(", "to_dict(",
    "to_series(", "write_csv(", "write_parquet(", "write_json(",
    "write_ndjson(", "clone(", "cast(", "map_batches(", "estimated_size(",
]

_POLARS_ALIASES = {"pl", "polars"}

# PySpark has two common dot-contexts: the SparkSession (`spark.`) and the
# functions module (usually aliased `F`). Both are alias-driven like pandas.
_PYSPARK_SESSION_METHODS = [
    "createDataFrame(", "read.csv(", "read.parquet(", "read.json(",
    "read.orc(", "read.table(", "read.format(", "sql(", "table(", "range(",
    "stop(", "newSession(", "catalog", "conf", "sparkContext", "udf",
    "streams", "version",
]
_PYSPARK_SESSION_ALIASES = {"spark"}

_PYSPARK_FUNCTIONS = [
    "col(", "lit(", "when(", "otherwise(", "coalesce(", "concat(",
    "concat_ws(", "substring(", "trim(", "upper(", "lower(", "length(",
    "split(", "regexp_replace(", "regexp_extract(", "to_date(",
    "to_timestamp(", "date_format(", "datediff(", "date_add(", "date_sub(",
    "year(", "month(", "dayofmonth(", "hour(", "sum(", "avg(", "count(",
    "countDistinct(", "min(", "max(", "first(", "last(", "collect_list(",
    "collect_set(", "struct(", "array(", "explode(", "expr(", "udf(",
    "row_number(", "rank(", "dense_rank(", "lag(", "lead(", "broadcast(",
    "monotonically_increasing_id(", "current_date(", "current_timestamp(",
    "isnull(", "isnan(", "greatest(", "least(", "round(", "abs(",
]
_PYSPARK_FUNCTIONS_ALIASES = {"F", "sf", "psf", "functions"}

_PYSPARK_DF_METHODS = [
    "show(", "printSchema(", "count(", "collect(", "take(", "first(",
    "head(", "select(", "selectExpr(", "withColumn(", "withColumns(",
    "withColumnRenamed(", "drop(", "filter(", "where(", "groupBy(", "agg(",
    "orderBy(", "sort(", "join(", "crossJoin(", "union(", "unionByName(",
    "intersect(", "subtract(", "distinct(", "dropDuplicates(", "na",
    "fillna(", "dropna(", "replace(", "alias(", "cache(", "persist(",
    "unpersist(", "repartition(", "coalesce(", "limit(", "sample(",
    "toPandas(", "toJSON(", "createOrReplaceTempView(",
    "createGlobalTempView(", "explain(", "columns", "dtypes", "schema",
    "rdd", "write.csv(", "write.parquet(", "write.json(", "write.mode(",
]

_POLARS_IMPORT_RE = re.compile(r"^\s*(import\s+polars\b|from\s+polars\b)", re.MULTILINE)
_PYSPARK_IMPORT_RE = re.compile(r"^\s*(import\s+pyspark\b|from\s+pyspark\b)", re.MULTILINE)

_DOT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)?$")
_IMPORT_RE = re.compile(r"^(\s*)import\s+(\w*)$")
_FROM_RE = re.compile(r"^(\s*)from\s+(\w*)$")

_IMPORT_CANDIDATES = ["pandas as pd", "polars as pl", "pyspark"]
_FROM_CANDIDATES = [
    "pandas import ",
    "polars import ",
    "pyspark.sql import SparkSession",
    "pyspark.sql import functions as F",
]


def _match(prefix: str, candidates: list[str]) -> str:
    """Return the remainder of the first candidate that starts with `prefix`."""
    for candidate in candidates:
        if candidate.startswith(prefix) and candidate != prefix:
            return candidate[len(prefix):]
    return ""


def _default_dataframe_methods(full_text: str, suffix: str) -> list[str]:
    """Fallback method list for a dot-chain on an unrecognised identifier.

    Picks the vocabulary by file suffix first (.polars is unambiguous), then
    by which library the file actually imports, defaulting to pandas.
    """
    if suffix == ".polars" or _POLARS_IMPORT_RE.search(full_text):
        return _POLARS_DF_METHODS
    if _PYSPARK_IMPORT_RE.search(full_text):
        return _PYSPARK_DF_METHODS
    return _DATAFRAME_METHODS


def _python_suggestion(line_before_cursor: str, full_text: str, suffix: str) -> str:
    """Ghost-text suggestion for pandas/Polars/PySpark code, given the text
    left of the cursor and the full document (used to infer the active
    library for generic, non-aliased dot-chains)."""
    if m := _DOT_RE.search(line_before_cursor):
        obj, prefix = m.group(1), m.group(2) or ""
        if obj in _PANDAS_ALIASES:
            return _match(prefix, _PANDAS_TOP_LEVEL)
        if obj in _POLARS_ALIASES:
            return _match(prefix, _POLARS_TOP_LEVEL)
        if obj in _PYSPARK_SESSION_ALIASES:
            return _match(prefix, _PYSPARK_SESSION_METHODS)
        if obj in _PYSPARK_FUNCTIONS_ALIASES:
            return _match(prefix, _PYSPARK_FUNCTIONS)
        if obj not in _NON_DATAFRAME_NAMES:
            return _match(prefix, _default_dataframe_methods(full_text, suffix))
        return ""
    if m := _IMPORT_RE.match(line_before_cursor):
        return _match(m.group(2), _IMPORT_CANDIDATES)
    if m := _FROM_RE.match(line_before_cursor):
        return _match(m.group(2), _FROM_CANDIDATES)
    return ""


class _DataFrameTextArea(TextArea):
    """TextArea that offers inline pandas/Polars/PySpark autocomplete for
    .py/.pandas/.polars files, and SQL/dbt autocomplete for .sql files."""

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 3 and not self.read_only:
            # Right click: move the cursor under the pointer and paste there,
            # instead of starting a text-selection drag like the left button does.
            # `action_paste()` reads Textual's own in-app clipboard (only ever
            # populated by copying inside this app), not the OS clipboard, so
            # the real system clipboard is fetched directly via pyperclip.
            try:
                text = pyperclip.paste()
            except pyperclip.PyperclipException:
                text = ""
            if text:
                self.selection = Selection.cursor(self.get_target_document_location(event))
                result = self.replace(text, *self.selection, maintain_selection_offset=False)
                self.move_cursor(result.end_location)
            event.stop()
            return
        await super()._on_mouse_down(event)

    def update_suggestion(self) -> None:
        editor = self.parent
        path = getattr(editor, "current_path", None)
        suffix = path.suffix.lower() if path is not None else ""
        if suffix not in (".py", ".pandas", ".sql"):
            self.suggestion = ""
            return
        if self.selection.start != self.selection.end:
            self.suggestion = ""
            return
        row, column = self.cursor_location
        line = self.get_line(row).plain[:column]
        if suffix == ".sql":
            self.suggestion = sql_tools.sql_suggestion(line)
        else:
            self.suggestion = _python_suggestion(line, self.text, suffix)


# ---------------------------------------------------------------- EditorPanel
class EditorPanel(Vertical):
    """Right pane: inline viewer/editor for code files and pandas-readable data files."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "run", "Run"),
        # Note: single real keystrokes only — TextArea/App already claim ctrl+a/c/d/e/
        # h/i/j/k/m/p/q/s/u/v/w/x/y/z (editing shortcuts, quit, command palette, ...),
        # and multi-part "ctrl+x+y"-style strings never fire from a real keyboard.
        Binding("ctrl+g", "cmd_pandas", "cmdPandas"),
        Binding("ctrl+o", "cmd_polars", "cmdPolars"),
        Binding("ctrl+t", "cmd_pyspark", "cmdPySpark"),
        Binding("ctrl+b", "cmd_dbt", "cmdDbt"),
    ]

    _RUNNABLE_SUFFIXES = {".py", ".pandas", ".polars", ".sql"}

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
            "Select a  .py  .sql  or data file (.csv .parquet .json .xlsx .csv.gz .zip …) in the left panel.",
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
            if formats.is_binary(path):
                content = self._dataframe_to_text(path)
            else:
                content = path.read_text(encoding="utf-8", errors="replace")

            if suffix in [".py", ".pandas", ".polars"]:
                area.language = "python"
            elif suffix == ".sql":
                area.language = "sql"
            else:
                area.language = None
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
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("cmd_pandas", "cmd_polars", "cmd_pyspark", "cmd_dbt", "run"):
            if self.current_path is None:
                return None
            # True when applicable, None to hide the binding from the footer.
            return True if self.current_path.suffix.lower() in self._RUNNABLE_SUFFIXES else None
        return True

    def _open_snippet_picker(self, library: str) -> None:
        """Pop up the snippet list for `library` (pandas/polars/pyspark/dbt) and
        insert the chosen snippet at the cursor."""
        title, catalog = snippets.LIBRARIES[library]

        def done(code: str | None) -> None:
            if code:
                self.query_one("#ep-area", TextArea).insert(code)

        self.app.push_screen(SnippetPickerScreen(title, catalog), done)

    def action_cmd_pandas(self) -> None:
        self._open_snippet_picker("pandas")

    def action_cmd_polars(self) -> None:
        self._open_snippet_picker("polars")

    def action_cmd_pyspark(self) -> None:
        self._open_snippet_picker("pyspark")

    def action_cmd_dbt(self) -> None:
        self._open_snippet_picker("dbt")

    # ------------------------------------------------------------------ action
    def action_run(self) -> None:
        if self.current_path is None:
            return

        if self.current_path.suffix.lower() == ".sql":
            self._run_sql()
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

    # -------------------------------------------------------------- run (SQL)
    def _run_sql(self) -> None:
        """Run the open .sql file (or the selection) via SQLAlchemy and show the result."""
        area = self.query_one("#ep-area", TextArea)
        result_table = self.query_one("#ep-result-table", DataTable)
        result_header = self.query_one("#ep-result-header", Static)
        result_table.clear(columns=True)

        def show_message(text: str, header: str) -> None:
            result_table.add_column("output")
            for line in text.splitlines():
                result_table.add_row(line)
            result_header.update(header)

        try:
            url = sql_tools.resolve_connection_url(self.current_path, area.text)
        except ImportError:
            show_message(
                "SQLAlchemy is not installed — cannot run .sql files.\n\n"
                "Install with:  pip install sqlalchemy",
                "Results — error",
            )
            return
        except sql_tools.SqlConfigError as exc:
            show_message(str(exc), "Results — database not configured")
            self.app.notify(
                "Configure the target database in db_connections.ini first.",
                severity="warning",
            )
            return

        # Run only the selection when there is one, otherwise the whole file.
        sql_text = area.selected_text or area.text
        try:
            run = sql_tools.run_sql(sql_text, url)
        except ImportError:
            show_message(
                "SQLAlchemy is not installed — cannot run .sql files.\n\n"
                "Install with:  pip install sqlalchemy",
                "Results — error",
            )
            return
        except Exception as exc:  # noqa: BLE001 - any DB/driver error goes to Results
            show_message(str(exc), "Results — error")
            return

        if run.columns:
            result_table.add_columns(*run.columns)
            for row in run.rows:
                result_table.add_row(*["" if v is None else str(v) for v in row])
        else:
            result_table.add_column("output")
            result_table.add_row(run.summary)
        result_header.update(f"Results  ({run.summary})")

    # ----------------------------------------------------------------- action
    def action_save(self) -> None:
        if self.current_path is None:
            return
        if formats.is_binary(self.current_path):
            self.app.notify(
                f"{self.current_path.suffix} files are a read-only preview and cannot be saved from the text editor.",
                severity="warning",
            )
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
        """Binary/compressed data files are a read-only preview, never auto-backed-up."""
        return path is not None and not formats.is_binary(path)

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
    def _dataframe_to_text(path: Path) -> str:
        try:
            df = formats.load_dataframe(path)
            return df.to_string()
        except ImportError as exc:
            packages = formats.required_packages(path)
            extra = " " + " ".join(packages) if packages else ""
            return (
                f"[missing dependency — cannot preview '{path.name}': {exc}]\n\n"
                f"Install with:  pip install pandas{extra}"
            )


class PandasEditorPanel(EditorPanel):
    """Right pane: inline viewer/editor for code files and pandas-readable data files.

    Identical to EditorPanel — kept as a distinct name for clarity at the call site
    in pandas-commander.py.
    """

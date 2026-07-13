from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------- configuration
# Target databases for .sql files live in an INI file next to the SQL file
# (or in the current working directory). Each section is a named connection,
# defined either by a full SQLAlchemy URL:
#
#   [default]
#   url = postgresql+psycopg2://user:pass@localhost:5432/mydb
#
# or by its components:
#
#   [default]
#   drivername = mysql+pymysql
#   username = user
#   password = secret
#   host = localhost
#   port = 3306
#   database = mydb
#
# The [default] section is used unless the SQL file contains a line like
# `-- connection: name` (checked anywhere in the file, first hit wins).
CONFIG_FILENAME = "db_connections.ini"

_CONN_DIRECTIVE_RE = re.compile(r"^\s*--\s*connection\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)

_URL_PARTS = ("drivername", "username", "password", "host", "port", "database")


class SqlConfigError(Exception):
    """Raised when no usable database connection is configured."""


def find_config(sql_path: Path) -> Path | None:
    """Locate db_connections.ini: next to the SQL file first, then the cwd."""
    for directory in (sql_path.parent, Path.cwd()):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def resolve_connection_url(sql_path: Path, sql_text: str) -> str:
    """Return the SQLAlchemy URL for `sql_path`, or raise SqlConfigError."""
    config_path = find_config(sql_path)
    if config_path is None:
        raise SqlConfigError(
            "No database configured for SQL files.\n"
            f"Create '{CONFIG_FILENAME}' next to the SQL file (or in the working directory)\n"
            "with a [default] section, e.g.:\n\n"
            "    [default]\n"
            "    url = sqlite:///example.db\n\n"
            "Any RDBMS supported by SQLAlchemy can be used as the url."
        )

    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except configparser.Error as exc:
        raise SqlConfigError(f"Cannot parse '{config_path}':\n{exc}") from exc

    sections = parser.sections()
    if not sections:
        raise SqlConfigError(
            f"'{config_path}' contains no connection.\n"
            "Add a [default] section, e.g.:\n\n"
            "    [default]\n"
            "    url = sqlite:///example.db"
        )

    directive = _CONN_DIRECTIVE_RE.search(sql_text)
    if directive:
        name = directive.group(1)
        if name not in sections:
            raise SqlConfigError(
                f"Connection '{name}' (from '-- connection: {name}') "
                f"is not defined in '{config_path}'.\n"
                f"Available: {', '.join(sections)}"
            )
    elif "default" in sections:
        name = "default"
    elif len(sections) == 1:
        name = sections[0]
    else:
        raise SqlConfigError(
            f"'{config_path}' defines several connections ({', '.join(sections)}) "
            "but no [default].\n"
            "Add a [default] section or put '-- connection: name' in the SQL file."
        )

    section = parser[name]
    if section.get("url"):
        return section["url"]
    if section.get("drivername"):
        from sqlalchemy.engine import URL  # noqa: PLC0415

        port = section.get("port")
        return URL.create(
            drivername=section["drivername"],
            username=section.get("username"),
            password=section.get("password"),
            host=section.get("host"),
            port=int(port) if port else None,
            database=section.get("database"),
        ).render_as_string(hide_password=False)
    raise SqlConfigError(
        f"Connection [{name}] in '{config_path}' has neither 'url' nor 'drivername'.\n"
        f"Set 'url = ...' or the parts: {', '.join(_URL_PARTS)}."
    )


# ------------------------------------------------------------- SQL execution
@dataclass
class SqlRunResult:
    """Outcome of running a SQL script: last result set (if any) + summary."""

    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    summary: str = ""
    truncated: bool = False


def split_statements(sql: str) -> list[str]:
    """Split a script on ';', respecting quotes and -- / /* */ comments."""
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            while i < n:
                buf.append(sql[i])
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # doubled quote escape
                        buf.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf.append(sql[i:j])
            i = j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            buf.append(sql[i:j])
            i = j
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement and _has_content(statement):
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    statement = "".join(buf).strip()
    if statement and _has_content(statement):
        statements.append(statement)
    return statements


def _has_content(statement: str) -> bool:
    """True if the statement contains anything besides comments/whitespace."""
    stripped = re.sub(r"--[^\n]*", "", statement)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    return bool(stripped.strip())


def run_sql(sql_text: str, url: str, max_rows: int = 1000) -> SqlRunResult:
    """Execute a SQL script against `url`; return the last result set.

    All statements run in one transaction (committed on success). DML/DDL
    row counts are aggregated into the summary when nothing returns rows.
    """
    from sqlalchemy import create_engine, text  # noqa: PLC0415

    statements = split_statements(sql_text)
    if not statements:
        return SqlRunResult(summary="nothing to execute")

    result = SqlRunResult()
    executed = 0
    affected = 0
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for statement in statements:
                cursor = conn.execute(text(statement))
                executed += 1
                if cursor.returns_rows:
                    fetched = cursor.fetchmany(max_rows + 1)
                    result.truncated = len(fetched) > max_rows
                    result.columns = [str(k) for k in cursor.keys()]
                    result.rows = [tuple(row) for row in fetched[:max_rows]]
                elif cursor.rowcount and cursor.rowcount > 0:
                    affected += cursor.rowcount
    finally:
        engine.dispose()

    if result.columns:
        result.summary = f"{len(result.rows)} rows × {len(result.columns)} cols"
        if result.truncated:
            result.summary += f" (first {max_rows} rows)"
    else:
        result.summary = f"{executed} statement(s) executed"
        if affected:
            result.summary += f", {affected} row(s) affected"
    return result


# ------------------------------------------------------- ANSI SQL autocomplete
# Ghost-text candidates for .sql files, in priority order — the first keyword
# matching the typed prefix (case-insensitively) wins. Ordered by frequency of
# use so short prefixes complete to the common keyword.
SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "DISTINCT",
    "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN",
    "CROSS JOIN", "ON", "AS", "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE",
    "IS NULL", "IS NOT NULL", "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
    "UNION", "UNION ALL", "INTERSECT", "EXCEPT", "LIMIT", "OFFSET",
    "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM",
    "CREATE TABLE", "CREATE VIEW", "CREATE INDEX", "ALTER TABLE",
    "DROP TABLE", "DROP VIEW", "DROP INDEX", "TRUNCATE TABLE",
    "PRIMARY KEY", "FOREIGN KEY", "REFERENCES", "NOT NULL", "UNIQUE",
    "DEFAULT", "CHECK", "CONSTRAINT",
    "COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "COALESCE(", "NULLIF(",
    "CAST(", "SUBSTRING(", "TRIM(", "UPPER(", "LOWER(", "LENGTH(", "ROUND(",
    "ABS(", "EXTRACT(", "POSITION(",
    "OVER(", "PARTITION BY", "ROW_NUMBER()", "RANK()", "DENSE_RANK()",
    "WITH", "RECURSIVE", "ASC", "DESC", "NULLS FIRST", "NULLS LAST",
    "CURRENT_DATE", "CURRENT_TIMESTAMP", "CURRENT_TIME",
    "INTEGER", "SMALLINT", "BIGINT", "DECIMAL(", "NUMERIC(", "FLOAT",
    "DOUBLE PRECISION", "REAL", "VARCHAR(", "CHAR(", "TEXT", "DATE",
    "TIMESTAMP", "TIME", "BOOLEAN", "INTERVAL",
    "NULL", "TRUE", "FALSE", "ALL", "ANY", "SOME",
    "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "BEGIN",
    "GROUPING SETS", "ROLLUP(", "CUBE(", "FETCH FIRST", "USING(",
]

_SQL_WORD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)$")


def sql_suggestion(line_before_cursor: str) -> str:
    """Ghost-text suggestion for ANSI SQL, given the text left of the cursor.

    The completion follows the typed case: `sel` -> `ect`, `SEL` -> `ECT`.
    """
    m = _SQL_WORD_RE.search(line_before_cursor)
    if m is None:
        return ""
    prefix = m.group(1)
    if len(prefix) < 2:  # single letters produce too much ghost noise
        return ""
    upper = prefix.upper()
    for keyword in SQL_KEYWORDS:
        if keyword.startswith(upper) and keyword != upper:
            rest = keyword[len(upper):]
            return rest.lower() if prefix.islower() else rest
    return ""

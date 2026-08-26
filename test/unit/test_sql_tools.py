"""Unit tests for panels/sql_tools.py — db_connections.ini resolution, SQL
statement splitting, execution via SQLAlchemy, and the SQL/dbt ghost-text
autocomplete."""
from __future__ import annotations

from pathlib import Path

import pytest

from panels import sql_tools

# ------------------------------------------------------------------ find_config

def test_find_config_prefers_directory_next_to_sql_file(tmp_path):
    sql_dir = tmp_path / "models"
    sql_dir.mkdir()
    (sql_dir / "db_connections.ini").write_text("[default]\nurl = sqlite://\n", encoding="utf-8")
    sql_path = sql_dir / "query.sql"
    sql_path.write_text("select 1;", encoding="utf-8")
    assert sql_tools.find_config(sql_path) == sql_dir / "db_connections.ini"


def test_find_config_falls_back_to_cwd(tmp_path, chdir_tmp):
    (chdir_tmp / "db_connections.ini").write_text("[default]\nurl = sqlite://\n", encoding="utf-8")
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    sql_path = other_dir / "query.sql"
    assert sql_tools.find_config(sql_path) == chdir_tmp / "db_connections.ini"


def test_find_config_none_when_absent(chdir_tmp):
    sql_path = chdir_tmp / "query.sql"
    assert sql_tools.find_config(sql_path) is None


# ----------------------------------------------------------- resolve_connection_url

def _write_ini(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_resolve_connection_url_no_config_raises(tmp_path, chdir_tmp):
    sql_path = tmp_path / "q.sql"
    with pytest.raises(sql_tools.SqlConfigError, match="No database configured"):
        sql_tools.resolve_connection_url(sql_path, "select 1;")


def test_resolve_connection_url_empty_ini_raises(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "")
    sql_path = tmp_path / "q.sql"
    with pytest.raises(sql_tools.SqlConfigError, match="contains no connection"):
        sql_tools.resolve_connection_url(sql_path, "select 1;")


def test_resolve_connection_url_malformed_ini_raises(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "not [valid ini{{")
    sql_path = tmp_path / "q.sql"
    with pytest.raises(sql_tools.SqlConfigError, match="Cannot parse"):
        sql_tools.resolve_connection_url(sql_path, "select 1;")


def test_resolve_connection_url_uses_default_section(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "[default]\nurl = sqlite:///x.db\n")
    sql_path = tmp_path / "q.sql"
    assert sql_tools.resolve_connection_url(sql_path, "select 1;") == "sqlite:///x.db"


def test_resolve_connection_url_single_non_default_section(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "[only]\nurl = sqlite:///y.db\n")
    sql_path = tmp_path / "q.sql"
    assert sql_tools.resolve_connection_url(sql_path, "select 1;") == "sqlite:///y.db"


def test_resolve_connection_url_multiple_sections_no_default_raises(tmp_path):
    _write_ini(
        tmp_path / "db_connections.ini",
        "[a]\nurl = sqlite:///a.db\n\n[b]\nurl = sqlite:///b.db\n",
    )
    sql_path = tmp_path / "q.sql"
    with pytest.raises(sql_tools.SqlConfigError, match="no \\[default\\]"):
        sql_tools.resolve_connection_url(sql_path, "select 1;")


def test_resolve_connection_url_connection_directive_selects_section(tmp_path):
    _write_ini(
        tmp_path / "db_connections.ini",
        "[default]\nurl = sqlite:///a.db\n\n[reporting]\nurl = sqlite:///b.db\n",
    )
    sql_path = tmp_path / "q.sql"
    sql_text = "-- connection: reporting\nselect 1;"
    assert sql_tools.resolve_connection_url(sql_path, sql_text) == "sqlite:///b.db"


def test_resolve_connection_url_unknown_connection_directive_raises(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "[default]\nurl = sqlite:///a.db\n")
    sql_path = tmp_path / "q.sql"
    sql_text = "-- connection: missing\nselect 1;"
    with pytest.raises(sql_tools.SqlConfigError, match="not defined"):
        sql_tools.resolve_connection_url(sql_path, sql_text)


def test_resolve_connection_url_builds_url_from_parts(tmp_path):
    _write_ini(
        tmp_path / "db_connections.ini",
        "[default]\n"
        "drivername = sqlite\n"
        "database = parts.db\n",
    )
    sql_path = tmp_path / "q.sql"
    url = sql_tools.resolve_connection_url(sql_path, "select 1;")
    assert "sqlite" in url
    assert "parts.db" in url


def test_resolve_connection_url_neither_url_nor_drivername_raises(tmp_path):
    _write_ini(tmp_path / "db_connections.ini", "[default]\nfoo = bar\n")
    sql_path = tmp_path / "q.sql"
    with pytest.raises(sql_tools.SqlConfigError, match="neither 'url' nor 'drivername'"):
        sql_tools.resolve_connection_url(sql_path, "select 1;")


# ------------------------------------------------------------- split_statements

def test_split_statements_basic():
    assert sql_tools.split_statements("select 1; select 2;") == ["select 1", "select 2"]


def test_split_statements_no_trailing_semicolon():
    assert sql_tools.split_statements("select 1") == ["select 1"]


def test_split_statements_ignores_semicolon_in_single_quotes():
    stmts = sql_tools.split_statements("select 'a;b' as x; select 2;")
    assert stmts == ["select 'a;b' as x", "select 2"]


def test_split_statements_ignores_semicolon_in_double_quotes():
    stmts = sql_tools.split_statements('select "a;b" as x;')
    assert stmts == ['select "a;b" as x']


def test_split_statements_handles_doubled_quote_escape():
    stmts = sql_tools.split_statements("select 'it''s; fine' as x;")
    assert stmts == ["select 'it''s; fine' as x"]


def test_split_statements_ignores_semicolon_in_line_comment():
    stmts = sql_tools.split_statements("select 1; -- comment; with semicolon\nselect 2;")
    assert stmts == ["select 1", "-- comment; with semicolon\nselect 2"]


def test_split_statements_ignores_semicolon_in_block_comment():
    stmts = sql_tools.split_statements("select 1 /* a; b */; select 2;")
    assert stmts == ["select 1 /* a; b */", "select 2"]


def test_split_statements_skips_comment_only_statements():
    stmts = sql_tools.split_statements("-- just a comment\n; select 1;")
    assert stmts == ["select 1"]


def test_split_statements_empty_input():
    assert sql_tools.split_statements("") == []


def test_split_statements_whitespace_only():
    assert sql_tools.split_statements("   \n\n  ") == []


# ------------------------------------------------------------------------ run_sql

def test_run_sql_no_statements_returns_summary():
    result = sql_tools.run_sql("-- nothing here", "sqlite://")
    assert result.summary == "nothing to execute"
    assert result.columns == []


def test_run_sql_select_returns_rows_and_columns(tmp_path):
    db_path = tmp_path / "t.db"
    url = f"sqlite:///{db_path}"
    sql = (
        "create table t (id integer, name text);"
        "insert into t values (1, 'a'), (2, 'b');"
        "select id, name from t order by id;"
    )
    result = sql_tools.run_sql(sql, url)
    assert result.columns == ["id", "name"]
    assert result.rows == [(1, "a"), (2, "b")]
    assert "2 rows" in result.summary
    assert result.truncated is False


def test_run_sql_ddl_dml_only_reports_affected_rows(tmp_path):
    db_path = tmp_path / "t2.db"
    url = f"sqlite:///{db_path}"
    sql = "create table t (id integer);insert into t values (1);insert into t values (2);"
    result = sql_tools.run_sql(sql, url)
    assert result.columns == []
    assert "3 statement(s) executed" in result.summary
    assert "2 row(s) affected" in result.summary


def test_run_sql_truncates_at_max_rows(tmp_path):
    db_path = tmp_path / "t3.db"
    url = f"sqlite:///{db_path}"
    values = ", ".join(f"({i})" for i in range(5))
    sql = f"create table t (id integer);insert into t values {values};select id from t;"
    result = sql_tools.run_sql(sql, url, max_rows=3)
    assert len(result.rows) == 3
    assert result.truncated is True
    assert "first 3 rows" in result.summary


def test_run_sql_error_propagates(tmp_path):
    db_path = tmp_path / "t4.db"
    url = f"sqlite:///{db_path}"
    with pytest.raises(Exception):
        sql_tools.run_sql("select * from no_such_table;", url)


# ---------------------------------------------------------------- sql_suggestion

@pytest.mark.parametrize(
    "line, expected",
    [
        ("sel", "ect"),   # all-lowercase prefix -> lowercase completion
        ("SEL", "ECT"),   # any non-lowercase prefix -> keyword's own (upper) case
        ("Sel", "ECT"),
        ("fr", "om"),
        ("gro", "up by"),
    ],
)
def test_sql_suggestion_matches_case_of_prefix(line, expected):
    assert sql_tools.sql_suggestion(line) == expected


def test_sql_suggestion_single_letter_suppressed():
    assert sql_tools.sql_suggestion("s") == ""


def test_sql_suggestion_no_match_returns_empty():
    assert sql_tools.sql_suggestion("zzz") == ""


def test_sql_suggestion_exact_keyword_no_suggestion():
    assert sql_tools.sql_suggestion("select") == ""


def test_sql_suggestion_empty_line():
    assert sql_tools.sql_suggestion("") == ""


def test_sql_suggestion_jinja_expr_context_offers_dbt_keywords():
    assert sql_tools.sql_suggestion("select {{ re") == "f('"


def test_sql_suggestion_jinja_stmt_context_offers_dbt_keywords():
    assert sql_tools.sql_suggestion("{% i") == "f "


def test_sql_suggestion_closed_jinja_tag_uses_normal_sql():
    # {{ ref('x') }} is closed, so plain SQL keyword completion applies after it.
    assert sql_tools.sql_suggestion("select {{ ref('x') }} fr") == "om"


def test_sql_suggestion_jinja_context_no_matching_keyword_returns_empty():
    assert sql_tools.sql_suggestion("{{ zzz") == ""


# ------------------------------------------------------------------- _has_content

def test_has_content_true_for_real_statement():
    assert sql_tools._has_content("select 1") is True


def test_has_content_false_for_comment_only():
    assert sql_tools._has_content("-- just a comment") is False


def test_has_content_false_for_block_comment_only():
    assert sql_tools._has_content("/* comment\nspanning lines */") is False

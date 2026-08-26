"""Unit tests for the pure ghost-text autocomplete helpers in
panels/EditorPanel.py (ep = the module's private ``_python_suggestion`` and
friends), independent of the TextArea widget itself."""
from __future__ import annotations

import pytest

from panels import EditorPanel as ep

# ------------------------------------------------------------------------ _match

def test_match_returns_remainder_of_first_candidate():
    assert ep._match("re", ["read_csv(", "read_excel("]) == "ad_csv("


def test_match_no_candidate_starts_with_prefix():
    assert ep._match("zzz", ["read_csv("]) == ""


def test_match_exact_equal_candidate_returns_empty():
    assert ep._match("read_csv(", ["read_csv("]) == ""


def test_match_empty_prefix_returns_first_candidate_in_full():
    assert ep._match("", ["head(", "tail("]) == "head("


# -------------------------------------------------------- _default_dataframe_methods

def test_default_dataframe_methods_polars_suffix():
    assert ep._default_dataframe_methods("", ".polars") is ep._POLARS_DF_METHODS


def test_default_dataframe_methods_polars_import_in_py_file():
    assert ep._default_dataframe_methods("import polars as pl\n", ".py") is ep._POLARS_DF_METHODS


def test_default_dataframe_methods_pyspark_import():
    assert ep._default_dataframe_methods("from pyspark.sql import SparkSession", ".py") is ep._PYSPARK_DF_METHODS


def test_default_dataframe_methods_falls_back_to_pandas():
    assert ep._default_dataframe_methods("import os\n", ".py") is ep._DATAFRAME_METHODS


def test_default_dataframe_methods_polars_suffix_wins_over_pyspark_import():
    # .polars files are unambiguous even if the text also mentions pyspark.
    text = "from pyspark.sql import functions as F\n"
    assert ep._default_dataframe_methods(text, ".polars") is ep._POLARS_DF_METHODS


# ------------------------------------------------------------------ _python_suggestion

def test_python_suggestion_pandas_alias_top_level():
    assert ep._python_suggestion("pd.read_c", "", ".py") == "sv("


def test_python_suggestion_polars_alias_top_level():
    assert ep._python_suggestion("pl.DataF", "", ".py") == "rame("


def test_python_suggestion_pyspark_session_alias():
    assert ep._python_suggestion("spark.createDataF", "", ".py") == "rame("


def test_python_suggestion_pyspark_functions_alias():
    assert ep._python_suggestion("F.upp", "", ".py") == "er("


def test_python_suggestion_non_dataframe_name_suppressed():
    assert ep._python_suggestion("os.pat", "", ".py") == ""


def test_python_suggestion_unknown_identifier_uses_default_methods():
    assert ep._python_suggestion("df.hea", "import pandas as pd\n", ".py") == "d("


def test_python_suggestion_unknown_identifier_polars_file():
    assert ep._python_suggestion("df.hea", "", ".polars") == "d("


def test_python_suggestion_import_statement():
    assert ep._python_suggestion("import pol", "", ".py") == "ars as pl"


def test_python_suggestion_from_statement():
    assert ep._python_suggestion("from pysp", "", ".py") == "ark.sql import SparkSession"


def test_python_suggestion_no_match_returns_empty():
    assert ep._python_suggestion("x = 1 + 2", "", ".py") == ""


def test_python_suggestion_dot_with_no_prefix_yet():
    assert ep._python_suggestion("pd.", "", ".py") == "DataFrame("


def test_python_suggestion_import_with_no_prefix():
    assert ep._python_suggestion("import ", "", ".py") == "pandas as pd"

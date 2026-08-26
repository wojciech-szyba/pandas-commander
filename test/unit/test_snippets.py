"""Unit tests for panels/snippets.py — snippet catalog integrity."""
from __future__ import annotations

import pytest

from panels import snippets

LIBRARY_NAMES = ["pandas", "polars", "pyspark", "dbt"]


def test_libraries_registry_has_all_expected_entries():
    assert set(snippets.LIBRARIES) == set(LIBRARY_NAMES)


@pytest.mark.parametrize("library", LIBRARY_NAMES)
def test_library_title_is_nonempty_string(library):
    title, _catalog = snippets.LIBRARIES[library]
    assert isinstance(title, str) and title


@pytest.mark.parametrize("library", LIBRARY_NAMES)
def test_library_catalog_entries_are_well_formed(library):
    _title, catalog = snippets.LIBRARIES[library]
    assert catalog, f"{library} catalog must not be empty"
    for key, value in catalog.items():
        assert isinstance(key, str) and key
        assert isinstance(value, tuple) and len(value) == 2
        label, code = value
        assert isinstance(label, str) and label
        assert isinstance(code, str) and code.strip()


def test_snippet_dedents_and_strips_blank_lines():
    _title, catalog = snippets.LIBRARIES["pandas"]
    label, code = catalog["profiling"]
    assert label == "Profiling summary"
    assert not code.startswith("\n")
    assert not code.endswith("\n")
    # dedent() should have removed the common leading indentation.
    for line in code.splitlines():
        if line.strip():
            assert not line.startswith("    " * 3)


def test_dbt_snippets_do_not_require_python_import():
    # dbt has no entry in EditorPanel._LIBRARY_IMPORT_LINES; make sure its
    # snippets are pure Jinja/SQL text, not Python.
    _title, catalog = snippets.LIBRARIES["dbt"]
    for _key, (_label, code) in catalog.items():
        assert "import " not in code.split("\n")[0] or "{{" in code


def test_pyspark_snippet_init_contains_sparksession():
    _title, catalog = snippets.LIBRARIES["pyspark"]
    _label, code = catalog["spark_init"]
    assert "SparkSession" in code
    assert "getOrCreate" in code

"""Shared pytest fixtures for the pandas-commander test suite.

Run from the repository root with:

    python -m pytest test

(pytest's ini-file discovery walks upward from the ``test`` argument, so
``test/pytest.ini`` is only picked up when ``test`` is on the command line —
running bare ``pytest`` from the repo root will not find it.)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ``panels`` and ``screens`` are plain packages living at the repo root; make
# sure that root is importable no matter what directory pytest is invoked from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_app_module():
    """Import pandas-commander.py (hyphenated filename, not a valid module name)."""
    spec = importlib.util.spec_from_file_location(
        "pandas_commander_app", ROOT / "pandas-commander.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def app_module():
    """The pandas-commander.py module (loaded once per test session)."""
    return _load_app_module()


@pytest.fixture
def PandasCommander(app_module):
    """The PandasCommander App class, with its recent-files path left alone.

    Most tests should use the ``isolated_app_class`` fixture instead, which
    also redirects RECENT_PATH away from the real user home directory.
    """
    return app_module.PandasCommander


@pytest.fixture
def isolated_app_class(app_module, tmp_path, monkeypatch):
    """PandasCommander class with RECENT_PATH redirected into a tmp dir.

    Prevents tests from reading/writing the developer's real
    ~/.pandas_commander_recent.json.
    """
    cls = app_module.PandasCommander
    monkeypatch.setattr(cls, "RECENT_PATH", tmp_path / ".pandas_commander_recent.json")
    return cls


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    """Run the test with cwd set to an empty tmp_path.

    Needed for code that discovers config files relative to the current
    working directory (remote_sources.find_config, sql_tools.find_config's
    cwd fallback) so tests never pick up this repository's own
    remote.ini / db_connections.ini.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def sample_tree(tmp_path):
    """A small directory tree exercising FilePanel's listing/filtering rules."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "script.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plain text", encoding="utf-8")
    # Autosave sidecar must never show up in the listing.
    (tmp_path / ".notes.txt.autosave").write_text("hidden", encoding="utf-8")
    return tmp_path

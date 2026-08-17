"""SQLite-backed shell command history for the command line (atuin-style):
every command run from #cmdline is recorded with its cwd and exit code, and
can be searched back through the history picker."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".pandas_commander_history.db"

# (command, last_ran_iso, last_cwd, last_exit_code, run_count)
HistoryRow = tuple[str, str, str, "int | None", int]


class CommandHistory:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                cwd TEXT NOT NULL,
                exit_code INTEGER,
                ran_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_history_command ON history(command)")
        self._conn.commit()

    def record(self, command: str, cwd: str, exit_code: int | None) -> None:
        self._conn.execute(
            "INSERT INTO history (command, cwd, exit_code, ran_at) VALUES (?, ?, ?, ?)",
            (command, cwd, exit_code, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self._conn.commit()

    def recent(self, limit: int = 500) -> list[HistoryRow]:
        """Most-recently-run commands first, deduplicated by command text."""
        cursor = self._conn.execute(
            """
            SELECT h1.command,
                   MAX(h1.ran_at) AS last_ran,
                   (SELECT h2.cwd FROM history h2
                      WHERE h2.command = h1.command ORDER BY h2.ran_at DESC LIMIT 1) AS last_cwd,
                   (SELECT h2.exit_code FROM history h2
                      WHERE h2.command = h1.command ORDER BY h2.ran_at DESC LIMIT 1) AS last_exit,
                   COUNT(*) AS runs
            FROM history h1
            GROUP BY h1.command
            ORDER BY last_ran DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def all_commands(self, limit: int = 1000) -> list[str]:
        """Distinct commands, most-recently-run first — used to seed autocompletion."""
        cursor = self._conn.execute(
            "SELECT command FROM history GROUP BY command ORDER BY MAX(ran_at) DESC LIMIT ?",
            (limit,),
        )
        return [row[0] for row in cursor.fetchall()]

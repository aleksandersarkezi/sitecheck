"""SQLite storage for monitor results.

One table, append-only: every monitor run adds one row per site. The web UI
reads the latest row per host and a short history for the trend.
SQLite is plenty for a few hundred sites checked a few times a day, and it's
one file on a Docker volume that's trivial to back up.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..models import SiteReport, report_to_dict

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    score INTEGER,
    grade TEXT,
    days_to_expiry INTEGER,
    fetch_error TEXT,
    report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checks_host_time ON checks (host, checked_at);
"""


@dataclass(frozen=True)
class StoredCheck:
    """One row from the `checks` table."""

    host: str
    checked_at: datetime
    score: int | None
    grade: str | None
    days_to_expiry: int | None
    fetch_error: str | None
    report: dict


class Store:
    """Thin wrapper around a SQLite file. Opens a new connection per operation,
    which keeps it safe to use from FastAPI's thread pool and the monitor."""

    def __init__(self, path: str | Path) -> None:
        # A real file is required: every operation opens its own connection,
        # so ":memory:" would give each one a fresh, empty database.
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            # WAL lets the web app read while the monitor writes.
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save(self, report: SiteReport, checked_at: datetime | None = None) -> None:
        when = (checked_at or datetime.now(UTC)).isoformat()
        days = report.tls.days_to_expiry if report.tls else None
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO checks (host, checked_at, score, grade, days_to_expiry, "
                "fetch_error, report_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    report.host,
                    when,
                    report.score,
                    report.grade,
                    days,
                    report.fetch_error,
                    json.dumps(report_to_dict(report)),
                ),
            )

    def latest(self, host: str) -> StoredCheck | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checks WHERE host = ? ORDER BY checked_at DESC, id DESC LIMIT 1",
                (host,),
            ).fetchone()
        return _row_to_check(row) if row else None

    def latest_all(self) -> list[StoredCheck]:
        """Most recent check for every host, sorted by host."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.* FROM checks c JOIN ("
                "  SELECT host, MAX(id) AS max_id FROM checks GROUP BY host"
                ") last ON c.id = last.max_id ORDER BY c.host"
            ).fetchall()
        return [_row_to_check(row) for row in rows]

    def history(self, host: str, limit: int = 30) -> list[StoredCheck]:
        """Newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checks WHERE host = ? ORDER BY checked_at DESC, id DESC LIMIT ?",
                (host, limit),
            ).fetchall()
        return [_row_to_check(row) for row in rows]

    def prune(self, keep_per_host: int = 200) -> int:
        """Delete old rows so the file doesn't grow forever. Returns rows removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM checks WHERE id IN ("
                "  SELECT id FROM ("
                "    SELECT id, ROW_NUMBER() OVER (PARTITION BY host ORDER BY id DESC) AS rn"
                "    FROM checks"
                "  ) WHERE rn > ?"
                ")",
                (keep_per_host,),
            )
            return cursor.rowcount


def _row_to_check(row: sqlite3.Row) -> StoredCheck:
    return StoredCheck(
        host=row["host"],
        checked_at=datetime.fromisoformat(row["checked_at"]),
        score=row["score"],
        grade=row["grade"],
        days_to_expiry=row["days_to_expiry"],
        fetch_error=row["fetch_error"],
        report=json.loads(row["report_json"]),
    )

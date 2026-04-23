"""SQLite-backed store for execution summaries.

The "notification" requirement (assignment R6) is satisfied by two sinks
firing on every execution:
  1. A structlog line on stdout — the terminal-facing notification.
  2. A row in this store — persistent trade history.

This file owns sink #2. It lives in the same SQLite file the
`SessionStore` uses so a Docker deployment only needs one volume mount.
The two stores are independent tables; neither depends on the other.

Design choices:
  - Full summary JSON goes into `summary_json` so reads are lossless.
  - Denormalized columns (broker, mode, placed, failed, created_at)
    exist so future filters — "only failed runs", "only zerodha",
    "today's trades" — are index lookups, not JSON scans.
  - Bounded growth: default 500-row cap. On insert, delete the oldest
    rows once the table exceeds the cap. Keeps the .sqlite file tiny
    and mirrors the old in-memory 100-row cap's bounded semantics.
  - No encryption. Order IDs and symbols are not sensitive the way
    broker access tokens are; they appear in the broker's own dashboard.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from src.schemas import ExecutionSummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    broker        TEXT NOT NULL,
    mode          TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    placed        INTEGER NOT NULL,
    failed        INTEGER NOT NULL,
    summary_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_created_at
    ON execution_events(created_at DESC);
"""

class EventStore:
    """Persistent, bounded, thread-safe ring buffer of execution summaries."""

    def __init__(self, db_path: Path, max_entries: int = 500) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._max_entries = max_entries
        self._lock = Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def append(self, summary: ExecutionSummary) -> None:
        row = (
            summary.broker,
            summary.mode,
            summary.started_at.isoformat(),
            summary.finished_at.isoformat(),
            len(summary.successes),
            len(summary.failures),
            summary.model_dump_json(),
            datetime.now(UTC).isoformat(),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_events (
                    broker, mode, started_at, finished_at, placed, failed,
                    summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

            conn.execute(
                """
                DELETE FROM execution_events
                WHERE id NOT IN (
                    SELECT id FROM execution_events
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (self._max_entries,),
            )

    def recent(self, limit: int | None = None) -> list[ExecutionSummary]:
        """Return most-recent-first summaries. `limit=None` returns everything."""
        sql = "SELECT summary_json FROM execution_events ORDER BY id DESC"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ExecutionSummary.model_validate(json.loads(r["summary_json"])) for r in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM execution_events")

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM execution_events"
            ).fetchone()
        return int(row["n"])

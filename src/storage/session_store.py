from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken

from src.schemas import BrokerSession


class SessionStoreError(Exception):
    pass

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    broker              TEXT NOT NULL,
    access_token_enc    BLOB NOT NULL,
    token_header_format TEXT NOT NULL,
    feed_token_enc      BLOB,
    refresh_token_enc   BLOB,
    user_id             TEXT,
    expires_at          TEXT,
    extras_json         TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_broker ON sessions(broker);
"""

class SessionStore:
    """SQLite-backed session store with Fernet encryption at rest.

    Tokens (`access_token`, `feed_token`, `refresh_token`) are never stored
    in plaintext. The Fernet key comes from the `FERNET_KEY` env var.
    Everything else (broker name, user_id, expires_at, extras) is stored
    plain for queryability — none of it is secret on its own.
    """

    def __init__(self, db_path: Path, fernet_key: str) -> None:
        if not fernet_key:
            raise SessionStoreError(
                "FERNET_KEY is required. Generate one with `make fernet-key`."
            )
        try:
            self._fernet = Fernet(fernet_key.encode())
        except (ValueError, TypeError) as exc:
            raise SessionStoreError(f"Invalid FERNET_KEY: {exc}") from exc

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _encrypt(self, value: str | None) -> bytes | None:
        if value is None:
            return None
        return self._fernet.encrypt(value.encode())

    def _decrypt(self, blob: bytes | None) -> str | None:
        if blob is None:
            return None
        try:
            return self._fernet.decrypt(blob).decode()
        except InvalidToken as exc:
            raise SessionStoreError(
                "Failed to decrypt token — FERNET_KEY likely changed since the "
                "session was saved. Re-authenticate."
            ) from exc

    def save(self, session: BrokerSession) -> str:
        """Persist a session and return its opaque session_id."""
        session_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, broker, access_token_enc, token_header_format,
                    feed_token_enc, refresh_token_enc, user_id, expires_at,
                    extras_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session.broker,
                    self._encrypt(session.access_token),
                    session.token_header_format,
                    self._encrypt(session.feed_token),
                    self._encrypt(session.refresh_token),
                    session.user_id,
                    session.expires_at.isoformat() if session.expires_at else None,
                    json.dumps(session.extras),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return session_id

    def load(self, session_id: str) -> BrokerSession:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise SessionStoreError(f"Unknown session_id={session_id!r}")

        return BrokerSession(
            broker=row["broker"],
            access_token=self._decrypt(row["access_token_enc"]) or "",
            token_header_format=row["token_header_format"],
            feed_token=self._decrypt(row["feed_token_enc"]),
            refresh_token=self._decrypt(row["refresh_token_enc"]),
            user_id=row["user_id"],
            expires_at=(
                datetime.fromisoformat(row["expires_at"])
                if row["expires_at"]
                else None
            ),
            extras=json.loads(row["extras_json"]),
        )

    def delete(self, session_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

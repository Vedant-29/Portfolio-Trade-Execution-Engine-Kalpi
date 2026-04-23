from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.schemas import BrokerSession
from src.storage import SessionStore, SessionStoreError


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    key = Fernet.generate_key().decode()
    return SessionStore(tmp_path / "sessions.sqlite", fernet_key=key)

def test_save_then_load_roundtrip(store: SessionStore) -> None:
    session = BrokerSession(
        broker="zerodha",
        access_token="secret-access",
        token_header_format="token {access_token}",
        user_id="AB1234",
        extras={"api_key": "xxx"},
    )
    sid = store.save(session)
    loaded = store.load(sid)
    assert loaded.broker == "zerodha"
    assert loaded.access_token == "secret-access"
    assert loaded.token_header_format == "token {access_token}"
    assert loaded.user_id == "AB1234"
    assert loaded.extras == {"api_key": "xxx"}

def test_load_unknown_session_id_raises(store: SessionStore) -> None:
    with pytest.raises(SessionStoreError, match="Unknown session_id"):
        store.load("nope")

def test_delete(store: SessionStore) -> None:
    sid = store.save(
        BrokerSession(broker="zerodha", access_token="t")
    )
    store.delete(sid)
    with pytest.raises(SessionStoreError):
        store.load(sid)

def test_tokens_encrypted_on_disk(store: SessionStore, tmp_path: Path) -> None:
    sid = store.save(
        BrokerSession(
            broker="angelone",
            access_token="jwt-abc-123",
            feed_token="feed-xyz-456",
            refresh_token="refresh-789",
        )
    )
    db_file = next(tmp_path.glob("sessions.sqlite"))
    raw = db_file.read_bytes()
    assert b"jwt-abc-123" not in raw
    assert b"feed-xyz-456" not in raw
    assert b"refresh-789" not in raw

    assert sid.encode() in raw
    assert b"angelone" in raw

def test_preserves_expires_at(store: SessionStore) -> None:
    when = datetime(2026, 4, 22, 15, 30, tzinfo=UTC)
    sid = store.save(
        BrokerSession(broker="upstox", access_token="t", expires_at=when)
    )
    loaded = store.load(sid)
    assert loaded.expires_at == when

def test_wrong_fernet_key_raises(tmp_path: Path) -> None:
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    s1 = SessionStore(tmp_path / "s.sqlite", fernet_key=k1)
    sid = s1.save(BrokerSession(broker="zerodha", access_token="secret"))
    s2 = SessionStore(tmp_path / "s.sqlite", fernet_key=k2)
    with pytest.raises(SessionStoreError, match="decrypt"):
        s2.load(sid)

def test_empty_fernet_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(SessionStoreError, match="FERNET_KEY is required"):
        SessionStore(tmp_path / "s.sqlite", fernet_key="")

def test_invalid_fernet_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(SessionStoreError, match="Invalid FERNET_KEY"):
        SessionStore(tmp_path / "s.sqlite", fernet_key="not-a-real-key")

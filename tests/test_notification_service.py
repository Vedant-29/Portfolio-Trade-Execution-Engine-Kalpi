"""Notification sinks — log + event store."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.schemas import (
    Action,
    Exchange,
    ExecutionSummary,
    OrderRequest,
    OrderResult,
)
from src.services import NotificationService
from src.storage import EventStore


def _sample_summary(broker: str = "fake") -> ExecutionSummary:
    req = OrderRequest(
        symbol="RELIANCE", exchange=Exchange.NSE, action=Action.BUY, quantity=1
    )
    return ExecutionSummary(
        broker=broker,
        mode="first_time",
        successes=[OrderResult.placed(req, broker_order_id="FAKE-1")],
        failures=[],
    )

@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "events.sqlite"

def test_store_sink_appends_summary(store_path: Path) -> None:
    store = EventStore(db_path=store_path, max_entries=100)
    svc = NotificationService(event_store=store)
    svc.notify(_sample_summary())
    assert len(store.recent()) == 1

def test_store_sink_cap_evicts_oldest(store_path: Path) -> None:
    store = EventStore(db_path=store_path, max_entries=3)
    svc = NotificationService(event_store=store)
    for i in range(5):
        svc.notify(_sample_summary(broker=f"b{i}"))
    recent = store.recent()
    assert [s.broker for s in recent] == ["b4", "b3", "b2"]

def test_store_sink_recent_limit_respected(store_path: Path) -> None:
    store = EventStore(db_path=store_path, max_entries=100)
    svc = NotificationService(event_store=store)
    for i in range(10):
        svc.notify(_sample_summary(broker=f"b{i}"))
    recent = store.recent(limit=3)
    assert len(recent) == 3
    assert [s.broker for s in recent] == ["b9", "b8", "b7"]

def test_log_sink_does_not_raise(store_path: Path) -> None:
    """Sanity check: notify() completes without exception for a
    successful summary. structlog output is not asserted on directly
    since the format is incidental."""
    store = EventStore(db_path=store_path, max_entries=100)
    svc = NotificationService(event_store=store)
    svc.notify(_sample_summary())

def test_store_persists_across_instances(store_path: Path) -> None:
    """A second EventStore pointed at the same file sees what the
    first one wrote. Guards against the old in-memory behavior
    creeping back in via a subtle refactor."""
    store_a = EventStore(db_path=store_path, max_entries=100)
    store_a.append(_sample_summary(broker="zerodha"))

    store_b = EventStore(db_path=store_path, max_entries=100)
    recent = store_b.recent()
    assert len(recent) == 1
    assert recent[0].broker == "zerodha"

def test_clear_removes_all_entries(store_path: Path) -> None:
    store = EventStore(db_path=store_path, max_entries=100)
    for i in range(3):
        store.append(_sample_summary(broker=f"b{i}"))
    assert store.count() == 3
    store.clear()
    assert store.count() == 0
    assert store.recent() == []

def test_rejects_invalid_max_entries(store_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        EventStore(db_path=store_path, max_entries=0)

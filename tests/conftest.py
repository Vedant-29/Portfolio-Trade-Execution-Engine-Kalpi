"""Shared test fixtures.

Provides a `FakeAdapter` — a programmable in-memory BrokerAdapter
implementation so ExecutionService tests run without any real broker.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.adapters import BrokerAdapter, registered_brokers
from src.adapters.registry import _reset_for_tests as reset_registry
from src.api.deps import _reset_for_tests as reset_deps
from src.schemas import BrokerSession, Holding, OrderRequest, OrderResult
from src.services import AuthService, ExecutionService, NotificationService
from src.storage import EventStore, SessionStore


class FakeAdapter(BrokerAdapter):
    """Deterministic, in-memory adapter for service-layer tests.

    Configure behavior per symbol by mutating class attributes before a
    test runs. By default every order is placed successfully with a
    predictable broker_order_id.
    """

    name = "fake"
    display_name = "Fake"
    auth_kind = "api_key_only"

    failures_by_symbol: dict[str, Exception] = {}
    order_log: list[OrderRequest] = []
    next_order_id: int = 0

    def authenticate_from_env(self) -> BrokerSession:
        return BrokerSession(broker="fake", access_token="fake-token")

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {"X-Fake": session.access_token}

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        self.order_log.append(req)
        exc = self.failures_by_symbol.get(req.symbol)
        if exc is not None:
            raise exc
        FakeAdapter.next_order_id += 1
        return OrderResult.placed(req, broker_order_id=f"FAKE-{FakeAdapter.next_order_id}")

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        return None

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        raise NotImplementedError

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        return []

@pytest.fixture
def fake_adapter_registered() -> Iterator[None]:
    """Register FakeAdapter under the name 'fake' for the duration of a test.

    Reset class-level state between tests so they don't leak — including
    `place_order`, which a few tests monkeypatch to simulate flaky behavior.
    """
    from src.adapters.registry import register

    reset_registry()
    FakeAdapter.failures_by_symbol = {}
    FakeAdapter.order_log = []
    FakeAdapter.next_order_id = 0

    FakeAdapter.place_order = _pristine_place_order
    register(FakeAdapter)
    yield
    reset_registry()
    FakeAdapter.place_order = _pristine_place_order

_pristine_place_order = FakeAdapter.place_order

@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    key = Fernet.generate_key().decode()
    return SessionStore(tmp_path / "sessions.sqlite", fernet_key=key)

@pytest.fixture
def auth_service(session_store: SessionStore) -> AuthService:
    return AuthService(
        session_store=session_store, public_base_url="http://test.local"
    )

@pytest.fixture
def event_store(tmp_path: Path) -> EventStore:
    return EventStore(db_path=tmp_path / "events.sqlite", max_entries=100)

@pytest.fixture
def notification_service(event_store: EventStore) -> NotificationService:
    return NotificationService(event_store=event_store)

@pytest.fixture
def execution_service(
    auth_service: AuthService, notification_service: NotificationService
) -> ExecutionService:
    return ExecutionService(
        auth_service=auth_service, notification_service=notification_service
    )

@pytest.fixture(autouse=True)
def _reset_cached_deps() -> None:
    """Clear the @lru_cache on FastAPI dep providers so each test starts
    clean. Prevents a SessionStore built in test A from leaking into test B."""
    reset_deps()

def _assert_brokers_registered() -> None:
    assert registered_brokers()

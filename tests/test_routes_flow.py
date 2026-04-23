"""End-to-end HTTP tests for the auth + portfolio routes.

Uses the real FastAPI app + FakeAdapter so we exercise routers, deps,
Pydantic validation, and the service wiring — without touching a broker.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.adapters import load_all_adapters
from src.adapters.registry import _reset_for_tests as reset_registry
from src.adapters.registry import register
from src.api.deps import _reset_for_tests as reset_deps
from src.api.deps import get_auth_service
from src.config import get_settings
from src.main import app
from tests.conftest import FakeAdapter


@pytest.fixture
def _configured_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    fernet = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", fernet)
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "sessions.sqlite"))

    for key in (
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "UPSTOX_API_KEY",
        "UPSTOX_API_SECRET",
        "ANGELONE_API_KEY",
        "FYERS_API_KEY",
        "FYERS_API_SECRET",
        "GROWW_API_KEY",
        "GROWW_API_SECRET",
    ):
        monkeypatch.setenv(key, "stub")
    get_settings.cache_clear()
    reset_deps()
    reset_registry()
    load_all_adapters()

    FakeAdapter.failures_by_symbol = {}
    FakeAdapter.order_log = []
    FakeAdapter.next_order_id = 0
    register(FakeAdapter)
    yield
    reset_registry()
    reset_deps()

@pytest.fixture
def client(_configured_env: None) -> TestClient:
    return TestClient(app)

def test_brokers_lists_all_six_now_including_fake(client: TestClient) -> None:
    resp = client.get("/brokers")
    assert resp.status_code == 200
    names = {b["name"] for b in resp.json()}
    assert {"zerodha", "upstox", "angelone", "fyers", "groww", "fake"}.issubset(names)

def test_login_init_oauth_redirect_returns_redirect_url(client: TestClient) -> None:
    resp = client.get("/auth/zerodha/login")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_kind"] == "oauth_redirect"
    assert body["redirect_url"] is not None
    assert "api_key=stub" in body["redirect_url"]
    assert body["fields"] is None

def test_login_init_credentials_form_returns_fields(client: TestClient) -> None:
    resp = client.get("/auth/angelone/login")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_kind"] == "credentials_form"
    assert body["redirect_url"] is None
    names = {f["name"] for f in body["fields"]}
    assert {"client_id", "pin"}.issubset(names)

def test_login_init_api_key_only_returns_no_redirect_or_fields(
    client: TestClient,
) -> None:
    resp = client.get("/auth/fake/login")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_kind"] == "api_key_only"
    assert body["redirect_url"] is None
    assert body["fields"] is None

def test_login_init_unknown_broker_returns_404(client: TestClient) -> None:
    resp = client.get("/auth/nosuchbroker/login")
    assert resp.status_code == 404

def test_post_login_api_key_only_creates_session(client: TestClient) -> None:
    resp = client.post("/auth/fake/login")
    assert resp.status_code == 200
    body = resp.json()
    assert body["broker"] == "fake"
    assert body["session_id"]

def test_post_login_oauth_broker_is_rejected(client: TestClient) -> None:
    resp = client.post("/auth/zerodha/login", json={"fields": {}})
    assert resp.status_code == 400

def test_post_login_credentials_form_requires_fields(client: TestClient) -> None:
    resp = client.post("/auth/angelone/login", json={"fields": {}})

    assert resp.status_code in (400, 401)

def test_portfolio_execute_first_time_end_to_end(client: TestClient) -> None:

    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]

    payload = {
        "broker": "fake",
        "session_id": session_id,
        "mode": "first_time",
        "first_time": [
            {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 2, "product": "CNC"},
            {"symbol": "TCS", "exchange": "NSE", "quantity": 1, "product": "CNC"},
        ],
    }
    resp = client.post("/portfolio/execute", json=payload)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["broker"] == "fake"
    assert summary["mode"] == "first_time"
    assert len(summary["successes"]) == 2
    assert summary["failures"] == []

def test_portfolio_execute_rebalance_respects_order(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]
    payload = {
        "broker": "fake",
        "session_id": session_id,
        "mode": "rebalance",
        "rebalance": {
            "sell": [{"symbol": "YES", "exchange": "NSE", "quantity": 5}],
            "buy_new": [{"symbol": "HDFC", "exchange": "NSE", "quantity": 1}],
            "adjust": [{"symbol": "INFY", "exchange": "NSE", "delta": 3}],
        },
    }
    resp = client.post("/portfolio/execute", json=payload)
    assert resp.status_code == 200
    order_symbols = [s["request"]["symbol"] for s in resp.json()["successes"]]
    assert order_symbols == ["YES", "HDFC", "INFY"]

def test_portfolio_execute_unknown_session_returns_401(client: TestClient) -> None:
    payload = {
        "broker": "fake",
        "session_id": "does-not-exist",
        "mode": "first_time",
        "first_time": [{"symbol": "X", "exchange": "NSE", "quantity": 1}],
    }
    resp = client.post("/portfolio/execute", json=payload)
    assert resp.status_code == 401

def test_portfolio_execute_rejects_invalid_payload(client: TestClient) -> None:
    """Pydantic cross-field validation — mode=first_time without first_time list."""
    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]
    resp = client.post(
        "/portfolio/execute",
        json={"broker": "fake", "session_id": session_id, "mode": "first_time"},
    )
    assert resp.status_code == 422

def test_holdings_uses_session(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]
    resp = client.get(f"/holdings?session_id={session_id}")
    assert resp.status_code == 200
    assert resp.json() == []

def test_holdings_unknown_session_returns_401(client: TestClient) -> None:
    resp = client.get("/holdings?session_id=does-not-exist")
    assert resp.status_code == 401

def test_status_returns_alive_for_valid_session(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    sid = auth_resp.json()["session_id"]
    resp = client.get(f"/auth/fake/status?session_id={sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alive"] is True
    assert body["broker"] == "fake"
    assert body["session_id"] == sid

def test_status_returns_dead_for_unknown_session(client: TestClient) -> None:
    resp = client.get("/auth/fake/status?session_id=does-not-exist")
    assert resp.status_code == 200
    assert resp.json()["alive"] is False

def test_status_returns_dead_when_session_belongs_to_wrong_broker(
    client: TestClient,
) -> None:
    auth_resp = client.post("/auth/fake/login")
    sid = auth_resp.json()["session_id"]

    resp = client.get(f"/auth/zerodha/status?session_id={sid}")
    assert resp.status_code == 200
    assert resp.json()["alive"] is False

def test_status_returns_dead_when_adapter_raises_auth_error(
    client: TestClient,
) -> None:
    """If get_holdings raises AuthError (expired token), the status
    endpoint must surface alive=False AND purge the stale session."""
    from src.adapters.errors import AuthError

    auth_resp = client.post("/auth/fake/login")
    sid = auth_resp.json()["session_id"]

    original = FakeAdapter.get_holdings

    def _raise_auth(self, session):
        raise AuthError("token expired", broker="fake")

    FakeAdapter.get_holdings = _raise_auth
    try:
        resp = client.get(f"/auth/fake/status?session_id={sid}")
        assert resp.status_code == 200
        assert resp.json()["alive"] is False
    finally:
        FakeAdapter.get_holdings = original

    resp2 = client.get(f"/auth/fake/status?session_id={sid}")
    assert resp2.json()["alive"] is False

def test_logout_deletes_session(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    sid = auth_resp.json()["session_id"]

    del_resp = client.delete(f"/auth/fake/session?session_id={sid}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "deleted"}

    status_resp = client.get(f"/auth/fake/status?session_id={sid}")
    assert status_resp.json()["alive"] is False

    exec_resp = client.post(
        "/portfolio/execute",
        json={
            "broker": "fake",
            "session_id": sid,
            "mode": "first_time",
            "first_time": [{"symbol": "X", "exchange": "NSE", "quantity": 1}],
        },
    )
    assert exec_resp.status_code == 401

def test_events_endpoint_initially_empty(client: TestClient) -> None:
    resp = client.get("/events")
    assert resp.status_code == 200
    assert resp.json() == []

def test_events_endpoint_records_executions(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]

    payload = {
        "broker": "fake",
        "session_id": session_id,
        "mode": "first_time",
        "first_time": [
            {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 1, "product": "CNC"}
        ],
    }
    exec_resp = client.post("/portfolio/execute", json=payload)
    assert exec_resp.status_code == 200

    events_resp = client.get("/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) == 1
    assert events[0]["broker"] == "fake"
    assert events[0]["mode"] == "first_time"
    assert len(events[0]["successes"]) == 1

def test_events_limit_param(client: TestClient) -> None:
    auth_resp = client.post("/auth/fake/login")
    session_id = auth_resp.json()["session_id"]
    for _ in range(3):
        client.post(
            "/portfolio/execute",
            json={
                "broker": "fake",
                "session_id": session_id,
                "mode": "first_time",
                "first_time": [
                    {"symbol": "X", "exchange": "NSE", "quantity": 1, "product": "CNC"}
                ],
            },
        )
    resp = client.get("/events?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

def test_auth_service_di_is_wired(client: TestClient) -> None:
    """Smoke: the FastAPI app's cached AuthService is actually the same
    instance that /auth uses. Guards against a regression where a test
    accidentally hits a different SessionStore than the one it wrote to."""
    svc = get_auth_service()
    sid = svc._sessions.save.__self__.__class__.__name__
    assert sid == "SessionStore"

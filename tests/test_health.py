from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.adapters import load_all_adapters
from src.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _ensure_adapters_loaded() -> None:
    """Other tests may reset the registry (test_registry.py isolates it
    per-test). The /health and /brokers routes read the live registry,
    so make sure it's populated here regardless of test ordering."""
    load_all_adapters()

_ORIGINAL_FIVE = {"zerodha", "upstox", "angelone", "fyers", "groww"}


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["brokers_configured"], list)
    assert _ORIGINAL_FIVE.issubset(set(body["brokers_registered"]))


def test_brokers_lists_original_five_with_correct_auth_kinds() -> None:
    response = client.get("/brokers")
    assert response.status_code == 200
    brokers = response.json()
    by_name = {b["name"]: b for b in brokers}
    assert _ORIGINAL_FIVE.issubset(set(by_name))
    assert by_name["zerodha"]["auth_kind"] == "oauth_redirect"
    assert by_name["upstox"]["auth_kind"] == "oauth_redirect"
    assert by_name["fyers"]["auth_kind"] == "oauth_redirect"
    assert by_name["angelone"]["auth_kind"] == "credentials_form"
    assert by_name["groww"]["auth_kind"] == "api_key_only"

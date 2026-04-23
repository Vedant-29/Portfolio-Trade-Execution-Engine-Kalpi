"""Smoke tests proving every registered adapter imports, constructs,
and satisfies the ABC contract. No network calls — these verify the
scaffolding only.

Assertions are written against a MINIMUM set of brokers (the five
originals) rather than an exact match. That way, when a new broker
is added via the /add-broker skill, these tests don't have to be
touched — the new broker just has to pass the same structural
checks as the others.
"""

from __future__ import annotations

import os

import pytest

from src.adapters import BrokerAdapter, all_adapter_classes, load_all_adapters
from src.adapters.registry import _reset_for_tests

_ORIGINAL_FIVE = {"zerodha", "upstox", "angelone", "fyers", "groww"}


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every adapter something plausible to construct from."""
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
        "PAYTM_API_KEY",
        "PAYTM_API_SECRET",
    ):
        monkeypatch.setenv(key, "stub")

    from src.config import get_settings

    get_settings.cache_clear()
    _reset_for_tests()


def test_load_all_adapters_registers_at_least_the_originals() -> None:
    names = set(load_all_adapters())
    assert _ORIGINAL_FIVE.issubset(names), (
        f"Expected at least {_ORIGINAL_FIVE}, got {names}"
    )


def test_each_adapter_is_a_subclass_of_the_abc() -> None:
    load_all_adapters()
    for name, cls in all_adapter_classes().items():
        assert issubclass(cls, BrokerAdapter), f"{name} does not extend BrokerAdapter"


def test_each_adapter_declares_required_classvars() -> None:
    load_all_adapters()
    for name, cls in all_adapter_classes().items():
        assert cls.name == name
        assert cls.display_name, f"{name} missing display_name"
        assert cls.auth_kind in {
            "oauth_redirect",
            "credentials_form",
            "api_key_only",
        }


def test_each_adapter_is_constructible_with_stub_credentials() -> None:
    load_all_adapters()
    for name, cls in all_adapter_classes().items():
        instance = cls()
        assert isinstance(instance, BrokerAdapter), f"{name} did not construct"


def test_credentials_form_adapter_exposes_fields() -> None:
    load_all_adapters()
    cls = all_adapter_classes()["angelone"]
    fields = cls().credential_fields()
    field_names = {f.name for f in fields}
    assert {"client_id", "pin"}.issubset(field_names)


def test_fyers_adapter_requires_secret_env() -> None:
    """Sanity check: constructors fail fast with a clear error when keys
    are missing. Guards against silent adapter-load failures in prod."""
    os.environ.pop("FYERS_API_KEY", None)
    os.environ.pop("FYERS_API_SECRET", None)
    from src.adapters.errors import AuthError
    from src.adapters.fyers import FyersAdapter
    from src.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(AuthError, match="FYERS_API_KEY"):
        FyersAdapter()

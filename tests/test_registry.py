from __future__ import annotations

import pytest

from src.adapters import (
    BrokerAdapter,
    FieldSpec,
    register,
    registered_brokers,
)
from src.adapters.registry import _reset_for_tests
from src.schemas import BrokerSession, Holding, OrderRequest, OrderResult


class _DummyAdapter(BrokerAdapter):
    """Concrete subclass filling only the universal methods; auth method
    groups are overridden in subclasses below to flex each auth_kind."""

    name = "dummy"
    display_name = "Dummy"
    auth_kind = "oauth_redirect"

    def build_login_url(self, redirect_uri: str, state: str) -> str:
        return f"{redirect_uri}?state={state}"

    def exchange_code_for_session(self, params):
        return BrokerSession(broker=self.name, access_token="tok")

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {"Authorization": f"Bearer {session.access_token}"}

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        return OrderResult.placed(req, broker_order_id="DUMMY-1")

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        return None

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        raise NotImplementedError

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        return []

@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    _reset_for_tests()

def test_register_oauth_adapter_ok() -> None:
    register(_DummyAdapter)
    assert registered_brokers() == ["dummy"]

def test_register_rejects_missing_oauth_methods() -> None:
    class BadOAuth(_DummyAdapter):
        name = "bad_oauth"

        build_login_url = BrokerAdapter.build_login_url

    with pytest.raises(TypeError, match="did not override build_login_url"):
        register(BadOAuth)

def test_register_credentials_form_adapter_ok() -> None:
    class CredsAdapter(_DummyAdapter):
        name = "creds"
        display_name = "Creds"
        auth_kind = "credentials_form"

        def credential_fields(self) -> list[FieldSpec]:
            return [FieldSpec(name="userid", label="User ID")]

        def authenticate_with_credentials(self, **fields: str) -> BrokerSession:
            return BrokerSession(broker=self.name, access_token="tok")

    register(CredsAdapter)
    assert "creds" in registered_brokers()

def test_register_credentials_form_missing_methods_rejected() -> None:
    class BadCreds(_DummyAdapter):
        name = "bad_creds"
        auth_kind = "credentials_form"

    with pytest.raises(TypeError, match="did not override credential_fields"):
        register(BadCreds)

def test_register_api_key_only_adapter_ok() -> None:
    class ApiKeyAdapter(_DummyAdapter):
        name = "apikey"
        display_name = "APIKey"
        auth_kind = "api_key_only"

        def authenticate_from_env(self) -> BrokerSession:
            return BrokerSession(broker=self.name, access_token="tok")

    register(ApiKeyAdapter)
    assert "apikey" in registered_brokers()

def test_register_rejects_unknown_auth_kind() -> None:
    class WeirdAdapter(_DummyAdapter):
        name = "weird"
        auth_kind = "magical"

    with pytest.raises(TypeError, match="unknown auth_kind"):
        register(WeirdAdapter)

def test_register_rejects_duplicate_names() -> None:
    register(_DummyAdapter)

    class Dup(_DummyAdapter):
        display_name = "Dup"

    with pytest.raises(TypeError, match="already registered"):
        register(Dup)

def test_register_usable_as_decorator() -> None:
    @register
    class DecoratedAdapter(_DummyAdapter):
        name = "decorated"
        display_name = "Decorated"

    assert "decorated" in registered_brokers()
    assert DecoratedAdapter.name == "decorated"

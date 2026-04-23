"""Zerodha-specific: AMO+MARKET combination rejected early, AMO+LIMIT
passes through to Kite with variety=amo."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.adapters.errors import AmoNotSupportedError
from src.adapters.zerodha.adapter import ZerodhaAdapter
from src.schemas import (
    Action,
    BrokerSession,
    Exchange,
    OrderRequest,
    PriceType,
    ProductType,
)


@pytest.fixture
def stub_adapter(monkeypatch: pytest.MonkeyPatch) -> ZerodhaAdapter:
    """Build a Zerodha adapter without requiring real env credentials."""
    adapter = ZerodhaAdapter.__new__(ZerodhaAdapter)
    adapter._api_key = "stub_key"
    adapter._api_secret = "stub_secret"
    return adapter

def _session() -> BrokerSession:
    return BrokerSession(
        broker="zerodha",
        access_token="stub_key:stub_token",
        token_header_format="token {access_token}",
    )

def test_amo_plus_market_is_rejected_before_hitting_kite(
    stub_adapter: ZerodhaAdapter,
) -> None:
    req = OrderRequest(
        symbol="IDEA",
        exchange=Exchange.NSE,
        action=Action.BUY,
        quantity=1,
        price_type=PriceType.MARKET,
        product=ProductType.CNC,
        amo=True,
    )
    with pytest.raises(AmoNotSupportedError) as exc_info:
        stub_adapter.place_order(_session(), req)
    assert exc_info.value.code == "AMO_NOT_SUPPORTED"
    assert exc_info.value.broker == "zerodha"

def test_amo_plus_limit_uses_variety_amo(
    stub_adapter: ZerodhaAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    kite_stub = MagicMock()
    kite_stub.place_order.return_value = "250423100001234"
    monkeypatch.setattr(stub_adapter, "_client", lambda _session: kite_stub)

    req = OrderRequest(
        symbol="IDEA",
        exchange=Exchange.NSE,
        action=Action.BUY,
        quantity=1,
        price_type=PriceType.LIMIT,
        product=ProductType.CNC,
        price=Decimal("9.50"),
        amo=True,
    )
    result = stub_adapter.place_order(_session(), req)
    assert result.status.value == "PLACED"
    assert result.broker_order_id == "250423100001234"

    kwargs = kite_stub.place_order.call_args.kwargs
    assert kwargs["variety"] == "amo"

    assert "market_protection" not in kwargs

def test_non_amo_market_still_sets_market_protection(
    stub_adapter: ZerodhaAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    kite_stub = MagicMock()
    kite_stub.place_order.return_value = "250423100005678"
    monkeypatch.setattr(stub_adapter, "_client", lambda _session: kite_stub)

    req = OrderRequest(
        symbol="IDEA",
        exchange=Exchange.NSE,
        action=Action.BUY,
        quantity=1,
        price_type=PriceType.MARKET,
        product=ProductType.CNC,
    )
    stub_adapter.place_order(_session(), req)
    kwargs = kite_stub.place_order.call_args.kwargs
    assert kwargs["variety"] == "regular"
    assert kwargs["market_protection"] == 5.0

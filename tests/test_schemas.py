from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schemas import (
    Action,
    AdjustItem,
    BuyItem,
    Exchange,
    FirstTimeItem,
    OrderRequest,
    OrderResult,
    OrderStatus,
    PortfolioExecuteRequest,
    PriceType,
    ProductType,
    RebalancePayload,
    SellItem,
)


class TestOrderRequest:
    def test_symbol_uppercased(self) -> None:
        req = OrderRequest(
            symbol="reliance",
            exchange=Exchange.NSE,
            action=Action.BUY,
            quantity=1,
        )
        assert req.symbol == "RELIANCE"

    def test_limit_order_requires_price(self) -> None:
        with pytest.raises(ValidationError, match="LIMIT orders require"):
            OrderRequest(
                symbol="TCS",
                exchange=Exchange.NSE,
                action=Action.BUY,
                quantity=1,
                price_type=PriceType.LIMIT,
            )

    def test_limit_order_with_price(self) -> None:
        req = OrderRequest(
            symbol="TCS",
            exchange=Exchange.NSE,
            action=Action.BUY,
            quantity=1,
            price_type=PriceType.LIMIT,
            price=Decimal("3500.25"),
        )
        assert req.price == Decimal("3500.25")

    def test_quantity_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="INFY",
                exchange=Exchange.NSE,
                action=Action.BUY,
                quantity=0,
            )

class TestOrderResult:
    def test_placed_helper(self) -> None:
        req = OrderRequest(
            symbol="RELIANCE", exchange=Exchange.NSE, action=Action.BUY, quantity=1
        )
        result = OrderResult.placed(req, broker_order_id="XYZ123")
        assert result.status == OrderStatus.PLACED
        assert result.broker_order_id == "XYZ123"
        assert result.error_message is None

    def test_failed_helper(self) -> None:
        req = OrderRequest(
            symbol="RELIANCE", exchange=Exchange.NSE, action=Action.BUY, quantity=1
        )
        result = OrderResult.failed(req, code="RATE_LIMIT", message="too many requests")
        assert result.status == OrderStatus.FAILED
        assert result.error_code == "RATE_LIMIT"
        assert result.broker_order_id is None

class TestPortfolioExecuteRequest:
    def test_first_time_requires_first_time_list(self) -> None:
        with pytest.raises(ValidationError, match="requires `first_time`"):
            PortfolioExecuteRequest(
                broker="zerodha",
                session_id="abc",
                mode="first_time",
            )

    def test_first_time_rejects_rebalance_payload(self) -> None:
        with pytest.raises(ValidationError, match="must not include `rebalance`"):
            PortfolioExecuteRequest(
                broker="zerodha",
                session_id="abc",
                mode="first_time",
                first_time=[
                    FirstTimeItem(
                        symbol="RELIANCE",
                        exchange=Exchange.NSE,
                        quantity=1,
                        product=ProductType.CNC,
                    )
                ],
                rebalance=RebalancePayload(
                    sell=[
                        SellItem(
                            symbol="TCS",
                            exchange=Exchange.NSE,
                            quantity=1,
                        )
                    ]
                ),
            )

    def test_rebalance_requires_rebalance_payload(self) -> None:
        with pytest.raises(ValidationError, match="requires `rebalance`"):
            PortfolioExecuteRequest(
                broker="zerodha",
                session_id="abc",
                mode="rebalance",
            )

    def test_rebalance_needs_at_least_one_instruction(self) -> None:
        with pytest.raises(ValidationError, match="at least one instruction"):
            RebalancePayload()

    def test_valid_first_time(self) -> None:
        req = PortfolioExecuteRequest(
            broker="zerodha",
            session_id="abc",
            mode="first_time",
            first_time=[
                FirstTimeItem(symbol="RELIANCE", exchange=Exchange.NSE, quantity=5),
                FirstTimeItem(symbol="TCS", exchange=Exchange.NSE, quantity=2),
            ],
        )
        assert len(req.first_time or []) == 2

    def test_valid_rebalance(self) -> None:
        req = PortfolioExecuteRequest(
            broker="zerodha",
            session_id="abc",
            mode="rebalance",
            rebalance=RebalancePayload(
                sell=[SellItem(symbol="YES", exchange=Exchange.NSE, quantity=100)],
                buy_new=[BuyItem(symbol="HDFC", exchange=Exchange.NSE, quantity=3)],
                adjust=[AdjustItem(symbol="TCS", exchange=Exchange.NSE, delta=-1)],
            ),
        )
        assert req.rebalance is not None
        assert len(req.rebalance.sell) == 1

class TestAdjustItem:
    def test_delta_nonzero(self) -> None:
        with pytest.raises(ValidationError, match="non-zero"):
            AdjustItem(symbol="TCS", exchange=Exchange.NSE, delta=0)

    def test_negative_delta(self) -> None:
        item = AdjustItem(symbol="TCS", exchange=Exchange.NSE, delta=-5)
        assert item.delta == -5

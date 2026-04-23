"""ExecutionService tests using FakeAdapter — no network."""

from __future__ import annotations

import pytest

from src.adapters.errors import (
    AuthError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
)
from src.schemas import (
    Action,
    AdjustItem,
    BrokerSession,
    BuyItem,
    Exchange,
    FirstTimeItem,
    OrderStatus,
    PortfolioExecuteRequest,
    ProductType,
    RebalancePayload,
    SellItem,
)
from src.services import AuthService, ExecutionService
from tests.conftest import FakeAdapter

pytestmark = pytest.mark.usefixtures("fake_adapter_registered")

def _save_fake_session(auth_service: AuthService) -> str:
    sid = auth_service._sessions.save(
        BrokerSession(broker="fake", access_token="tok")
    )
    return sid

def test_first_time_places_buy_for_every_item(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(symbol="RELIANCE", exchange=Exchange.NSE, quantity=5),
            FirstTimeItem(symbol="TCS", exchange=Exchange.NSE, quantity=2),
            FirstTimeItem(symbol="INFY", exchange=Exchange.NSE, quantity=10),
        ],
    )

    summary = execution_service.execute(req)

    assert len(summary.successes) == 3
    assert summary.failures == []
    for r in summary.successes:
        assert r.status is OrderStatus.PLACED
        assert r.request.action is Action.BUY
    assert [o.symbol for o in FakeAdapter.order_log] == ["RELIANCE", "TCS", "INFY"]

def test_first_time_honors_product_type(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(
                symbol="SBIN",
                exchange=Exchange.NSE,
                quantity=1,
                product=ProductType.MIS,
            )
        ],
    )
    summary = execution_service.execute(req)
    assert summary.successes[0].request.product is ProductType.MIS

def test_rebalance_flattens_in_sell_buy_adjust_order(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    """Critical architectural invariant: SELL → BUY_NEW → ADJUST.
    Sells free up capital before any buy."""
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="rebalance",
        rebalance=RebalancePayload(
            sell=[SellItem(symbol="YESBANK", exchange=Exchange.NSE, quantity=100)],
            buy_new=[BuyItem(symbol="HDFCBANK", exchange=Exchange.NSE, quantity=3)],
            adjust=[
                AdjustItem(symbol="RELIANCE", exchange=Exchange.NSE, delta=+2),
                AdjustItem(symbol="TCS", exchange=Exchange.NSE, delta=-1),
            ],
        ),
    )

    summary = execution_service.execute(req)
    placed_symbols = [r.request.symbol for r in summary.successes]
    assert placed_symbols == ["YESBANK", "HDFCBANK", "RELIANCE", "TCS"]

    by_sym = {r.request.symbol: r.request for r in summary.successes}
    assert by_sym["YESBANK"].action is Action.SELL
    assert by_sym["HDFCBANK"].action is Action.BUY
    assert by_sym["RELIANCE"].action is Action.BUY
    assert by_sym["RELIANCE"].quantity == 2
    assert by_sym["TCS"].action is Action.SELL
    assert by_sym["TCS"].quantity == 1

def test_rebalance_empty_lists_only_executes_the_non_empty_group(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="rebalance",
        rebalance=RebalancePayload(
            buy_new=[BuyItem(symbol="HDFCBANK", exchange=Exchange.NSE, quantity=3)],
        ),
    )
    summary = execution_service.execute(req)
    assert [r.request.symbol for r in summary.successes] == ["HDFCBANK"]

def test_one_failing_order_does_not_kill_the_batch(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    FakeAdapter.failures_by_symbol = {
        "BAD_SYMBOL": InvalidOrderError("no such stock", broker="fake"),
    }
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(symbol="RELIANCE", exchange=Exchange.NSE, quantity=1),
            FirstTimeItem(symbol="BAD_SYMBOL", exchange=Exchange.NSE, quantity=1),
            FirstTimeItem(symbol="INFY", exchange=Exchange.NSE, quantity=1),
        ],
    )
    summary = execution_service.execute(req)

    assert {r.request.symbol for r in summary.successes} == {"RELIANCE", "INFY"}
    assert len(summary.failures) == 1
    failure = summary.failures[0]
    assert failure.request.symbol == "BAD_SYMBOL"
    assert failure.status is OrderStatus.FAILED
    assert failure.error_message == "no such stock"

def test_retryable_errors_are_retried_then_surface_as_failures_when_exhausted(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    FakeAdapter.failures_by_symbol = {
        "FLAKY": RateLimitError("429", broker="fake"),
    }
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(symbol="FLAKY", exchange=Exchange.NSE, quantity=1),
        ],
    )
    summary = execution_service.execute(req)
    assert len(summary.failures) == 1

    assert len([o for o in FakeAdapter.order_log if o.symbol == "FLAKY"]) == 3

def test_transient_errors_retry_and_can_succeed(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    attempts = {"n": 0}

    def flaky_failure(self, session, req):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TransientBrokerError("timeout", broker="fake")
        FakeAdapter.next_order_id += 1
        from src.schemas import OrderResult

        return OrderResult.placed(req, broker_order_id=f"FAKE-{FakeAdapter.next_order_id}")

    FakeAdapter.place_order = flaky_failure
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[FirstTimeItem(symbol="RELIANCE", exchange=Exchange.NSE, quantity=1)],
    )
    summary = execution_service.execute(req)
    assert len(summary.successes) == 1
    assert summary.failures == []
    assert attempts["n"] == 2

def test_session_broker_mismatch_raises(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = auth_service._sessions.save(
        BrokerSession(broker="zerodha", access_token="tok")
    )
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[FirstTimeItem(symbol="X", exchange=Exchange.NSE, quantity=1)],
    )
    from src.adapters.errors import BrokerError

    with pytest.raises(BrokerError, match="Session belongs to broker"):
        execution_service.execute(req)

def test_auth_error_propagates(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    FakeAdapter.failures_by_symbol = {"X": AuthError("expired", broker="fake")}
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[FirstTimeItem(symbol="X", exchange=Exchange.NSE, quantity=1)],
    )

    summary = execution_service.execute(req)
    assert len(summary.failures) == 1
    assert summary.failures[0].error_code in {"AuthError", None}

def test_amo_flag_threads_through_first_time(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(
                symbol="IDEA",
                exchange=Exchange.NSE,
                quantity=1,
                amo=True,
            ),
            FirstTimeItem(
                symbol="YESBANK",
                exchange=Exchange.NSE,
                quantity=1,

            ),
        ],
    )
    execution_service.execute(req)
    assert FakeAdapter.order_log[0].amo is True
    assert FakeAdapter.order_log[1].amo is False

def test_amo_flag_threads_through_rebalance(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="rebalance",
        rebalance=RebalancePayload(
            sell=[
                SellItem(
                    symbol="IDEA", exchange=Exchange.NSE, quantity=1, amo=True
                )
            ],
            buy_new=[
                BuyItem(
                    symbol="SOUTHBANK", exchange=Exchange.NSE, quantity=1, amo=True
                )
            ],
            adjust=[
                AdjustItem(
                    symbol="YESBANK", exchange=Exchange.NSE, delta=1, amo=True
                )
            ],
        ),
    )
    execution_service.execute(req)
    assert len(FakeAdapter.order_log) == 3
    for order in FakeAdapter.order_log:
        assert order.amo is True

def test_insufficient_funds_is_classified_not_unexpected(
    auth_service: AuthService, execution_service: ExecutionService
) -> None:
    """A raw Exception leaking from an adapter with an 'Insufficient funds'
    message should come back as INSUFFICIENT_FUNDS, not UNEXPECTED_ERROR."""
    class _RawInsufficientFunds(Exception):
        pass

    FakeAdapter.failures_by_symbol = {
        "RELIANCE": _RawInsufficientFunds(
            "Insufficient funds. Required margin is 1421.20 "
            "but available margin is 0.00."
        )
    }
    sid = _save_fake_session(auth_service)
    req = PortfolioExecuteRequest(
        broker="fake",
        session_id=sid,
        mode="first_time",
        first_time=[
            FirstTimeItem(symbol="RELIANCE", exchange=Exchange.NSE, quantity=1),
        ],
    )
    summary = execution_service.execute(req)
    assert len(summary.failures) == 1
    assert summary.failures[0].error_code == "INSUFFICIENT_FUNDS"

"""Execution orchestration — the heart of the engine.

Responsibilities:
  1. Resolve the session_id to a live BrokerSession.
  2. Look up the matching adapter.
  3. Flatten the request payload into a deterministic ordered list of
     canonical OrderRequests.
  4. For each order, call adapter.place_order with retry-on-transient.
  5. Collect per-order results into an ExecutionSummary.
  6. Never let one bad order kill the batch (per-order isolation).

Rebalance ordering rule (load-bearing design choice — see README):
  SELL first → BUY_NEW next → ADJUST last. Selling first frees up
  capital for subsequent buys; doing it any other way risks rejects
  on cash accounts.
"""

from __future__ import annotations

from src.adapters import BrokerAdapter, get_adapter
from src.adapters.errors import BrokerError, classify_message
from src.schemas import (
    Action,
    BrokerSession,
    ExecutionSummary,
    OrderRequest,
    OrderResult,
    OrderStatus,
    PortfolioExecuteRequest,
    RebalancePayload,
)
from src.services.auth_service import AuthService
from src.services.notification_service import NotificationService
from src.utils.logging import get_logger
from src.utils.retry import with_retry

_logger = get_logger(__name__)

class ExecutionService:
    def __init__(
        self,
        *,
        auth_service: AuthService,
        notification_service: NotificationService,
    ) -> None:
        self._auth = auth_service
        self._notifications = notification_service

    def execute(self, req: PortfolioExecuteRequest) -> ExecutionSummary:
        session = self._auth.resolve(req.session_id)
        if session.broker != req.broker:
            raise BrokerError(
                f"Session belongs to broker={session.broker!r} but request "
                f"asked for broker={req.broker!r}",
                broker=req.broker,
            )
        adapter = get_adapter(req.broker)()
        orders = self._flatten(req)
        _logger.info(
            "execution_start",
            broker=req.broker,
            mode=req.mode,
            order_count=len(orders),
        )
        summary = ExecutionSummary(broker=req.broker, mode=req.mode)
        for order in orders:
            result = self._place_one(adapter, session, order)
            if result.status is OrderStatus.PLACED:
                summary.successes.append(result)
            else:
                summary.failures.append(result)

        _logger.info(
            "execution_done",
            broker=req.broker,
            mode=req.mode,
            placed=len(summary.successes),
            failed=len(summary.failures),
        )

        self._notifications.notify(summary)
        return summary

    @staticmethod
    def _flatten(req: PortfolioExecuteRequest) -> list[OrderRequest]:
        if req.mode == "first_time":
            assert req.first_time is not None
            return [
                OrderRequest(
                    symbol=item.symbol,
                    exchange=item.exchange,
                    action=Action.BUY,
                    quantity=item.quantity,
                    product=item.product,
                    amo=item.amo,
                )
                for item in req.first_time
            ]

        assert req.rebalance is not None
        return ExecutionService._flatten_rebalance(req.rebalance)

    @staticmethod
    def _flatten_rebalance(payload: RebalancePayload) -> list[OrderRequest]:
        """SELL → BUY_NEW → ADJUST. See the rebalance-ordering rule above."""
        orders: list[OrderRequest] = []

        for s in payload.sell:
            orders.append(
                OrderRequest(
                    symbol=s.symbol,
                    exchange=s.exchange,
                    action=Action.SELL,
                    quantity=s.quantity,
                    product=s.product,
                    amo=s.amo,
                )
            )
        for b in payload.buy_new:
            orders.append(
                OrderRequest(
                    symbol=b.symbol,
                    exchange=b.exchange,
                    action=Action.BUY,
                    quantity=b.quantity,
                    product=b.product,
                    amo=b.amo,
                )
            )
        for a in payload.adjust:
            action = Action.BUY if a.delta > 0 else Action.SELL
            orders.append(
                OrderRequest(
                    symbol=a.symbol,
                    exchange=a.exchange,
                    action=action,
                    quantity=abs(a.delta),
                    product=a.product,
                    amo=a.amo,
                )
            )
        return orders

    @staticmethod
    def _place_one(
        adapter: BrokerAdapter,
        session: BrokerSession,
        req: OrderRequest,
    ) -> OrderResult:
        try:
            return with_retry(lambda: adapter.place_order(session, req))
        except BrokerError as exc:

            _logger.warning(
                "order_failed",
                broker=adapter.name,
                symbol=req.symbol,
                action=req.action.value,
                error_type=type(exc).__name__,
                error_code=exc.code,
                error_message=str(exc),
            )
            return OrderResult.failed(
                req,
                code=exc.code or type(exc).__name__,
                message=str(exc),
            )
        except Exception as exc:

            classified = classify_message(
                str(exc),
                broker=adapter.name,
                fallback_code="ORDER_REJECTED",
            )

            _logger.warning(
                "order_failed",
                broker=adapter.name,
                symbol=req.symbol,
                action=req.action.value,
                error_code=classified.code,
                error_message=str(exc),
            )
            return OrderResult.failed(
                req,
                code=classified.code or "ORDER_REJECTED",
                message=str(exc),
            )

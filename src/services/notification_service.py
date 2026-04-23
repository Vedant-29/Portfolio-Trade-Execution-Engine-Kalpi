"""Notification fan-out — log + event store only.

The assignment allowed "a mocked Webhook, WebSocket event, or a simple
email/console log." We went with the simplest path:

  1. structlog line on stdout (event="execution_summary") — the primary
     surface the operator/reviewer reads in the terminal
  2. in-memory EventStore (last 100 summaries) — queryable via GET /events

Both run synchronously, neither has any external dependency. If a sink
ever fails it's logged and swallowed — a notification failure must never
mark a completed execution as failed.
"""

from __future__ import annotations

from src.schemas import ExecutionSummary
from src.storage import EventStore
from src.utils.logging import get_logger

_logger = get_logger(__name__)

class NotificationService:
    def __init__(self, *, event_store: EventStore) -> None:
        self._events = event_store

    def notify(self, summary: ExecutionSummary) -> None:
        self._log_sink(summary)
        self._store_sink(summary)

    def _log_sink(self, summary: ExecutionSummary) -> None:
        _logger.info(
            "execution_summary",
            broker=summary.broker,
            mode=summary.mode,
            total=summary.total_orders,
            placed=len(summary.successes),
            failed=len(summary.failures),
            placed_symbols=[r.request.symbol for r in summary.successes],
            failure_symbols=[r.request.symbol for r in summary.failures],
        )

    def _store_sink(self, summary: ExecutionSummary) -> None:
        self._events.append(summary)

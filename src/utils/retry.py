from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.adapters.errors import RateLimitError, TransientBrokerError
from src.utils.logging import get_logger

T = TypeVar("T")
_logger = get_logger(__name__)

def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    _logger.warning(
        "broker_retry",
        attempt=state.attempt_number,
        exception_type=type(exc).__name__ if exc else None,
        exception_msg=str(exc) if exc else None,
    )

def with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
) -> T:
    """Run `func` with exponential-jitter backoff on retryable broker errors.

    Retries on RateLimitError and TransientBrokerError only. Everything else
    (AuthError, InvalidOrderError, InsufficientFundsError, ValueError, ...)
    propagates immediately.

    Usage:
        result = with_retry(lambda: adapter.place_order(session, req))
    """

    retrier = retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=base_delay, max=max_delay),
        retry=retry_if_exception_type((RateLimitError, TransientBrokerError)),
        before_sleep=_log_retry,
    )
    return retrier(func)()

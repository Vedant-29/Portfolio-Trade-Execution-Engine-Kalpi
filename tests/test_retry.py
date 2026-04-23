from __future__ import annotations

import pytest

from src.adapters.errors import (
    AuthError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
)
from src.utils.retry import with_retry


def test_returns_result_on_first_success() -> None:
    calls = {"n": 0}

    def op() -> str:
        calls["n"] += 1
        return "ok"

    assert with_retry(op) == "ok"
    assert calls["n"] == 1

def test_retries_on_rate_limit_then_succeeds() -> None:
    attempts = {"n": 0}

    def op() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimitError("429", code="RATE_LIMIT", broker="zerodha")
        return "ok"

    assert with_retry(op, max_attempts=5, base_delay=0.01, max_delay=0.05) == "ok"
    assert attempts["n"] == 3

def test_retries_on_transient_then_succeeds() -> None:
    attempts = {"n": 0}

    def op() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TransientBrokerError("500", code="SERVER_ERR")
        return "ok"

    assert with_retry(op, max_attempts=3, base_delay=0.01, max_delay=0.05) == "ok"

def test_gives_up_after_max_attempts() -> None:
    attempts = {"n": 0}

    def op() -> str:
        attempts["n"] += 1
        raise RateLimitError("429")

    with pytest.raises(RateLimitError):
        with_retry(op, max_attempts=3, base_delay=0.01, max_delay=0.05)
    assert attempts["n"] == 3

def test_does_not_retry_auth_error() -> None:
    attempts = {"n": 0}

    def op() -> str:
        attempts["n"] += 1
        raise AuthError("invalid token")

    with pytest.raises(AuthError):
        with_retry(op, max_attempts=5, base_delay=0.01, max_delay=0.05)
    assert attempts["n"] == 1

def test_does_not_retry_invalid_order() -> None:
    attempts = {"n": 0}

    def op() -> str:
        attempts["n"] += 1
        raise InvalidOrderError("bad symbol")

    with pytest.raises(InvalidOrderError):
        with_retry(op, max_attempts=5, base_delay=0.01, max_delay=0.05)
    assert attempts["n"] == 1

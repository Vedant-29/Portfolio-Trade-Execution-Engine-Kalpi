"""Tests for the pattern-based error classifier.

These are regression-critical — the classifier is how Kite's raw error
text "Insufficient funds. Required margin is X..." becomes a typed
InsufficientFundsError in our taxonomy, which is what lets the UI
render a friendly label instead of UNEXPECTED_ERROR.
"""

from __future__ import annotations

import pytest

from src.adapters.errors import (
    AmoNotSupportedError,
    AuthError,
    CircuitLimitError,
    InsufficientFundsError,
    InvalidOrderError,
    InvalidSymbolError,
    MarketClosedError,
    RateLimitError,
    classify_message,
)


@pytest.mark.parametrize(
    "message, expected_class, expected_code",
    [
        (
            "Insufficient funds. Required margin is 1421.20 but available margin is 0.00.",
            InsufficientFundsError,
            "INSUFFICIENT_FUNDS",
        ),
        (
            "Required margin: 500, you have 100",
            InsufficientFundsError,
            "INSUFFICIENT_FUNDS",
        ),
        ("Market is closed", MarketClosedError, "MARKET_CLOSED"),
        (
            "Your order could not be converted to a After Market Order (AMO).",
            MarketClosedError,
            "MARKET_CLOSED",
        ),
        (
            "Upper circuit hit for this scrip",
            CircuitLimitError,
            "CIRCUIT_LIMIT_UPPER",
        ),
        (
            "Lower circuit hit",
            CircuitLimitError,
            "CIRCUIT_LIMIT_LOWER",
        ),
        ("Invalid symbol RELIANC", InvalidSymbolError, "INVALID_SYMBOL"),
        (
            "Unknown instrument: XXXX",
            InvalidSymbolError,
            "INVALID_SYMBOL",
        ),
        ("Symbol not found", InvalidSymbolError, "INVALID_SYMBOL"),
        ("Rate limit exceeded", RateLimitError, "RATE_LIMIT"),
        ("Too many requests", RateLimitError, "RATE_LIMIT"),
        ("Session token expired", AuthError, "AUTH_EXPIRED"),
        (
            "No IPs configured for this app. Add allowed IPs on the Kite developer console.",
            AuthError,
            "IP_NOT_WHITELISTED",
        ),
        (
            "IP not allowed to place orders for this app",
            AuthError,
            "IP_NOT_WHITELISTED",
        ),
    ],
)
def test_classify_message_known_patterns(
    message: str, expected_class: type, expected_code: str
) -> None:
    err = classify_message(message, broker="zerodha")
    assert isinstance(err, expected_class)
    assert err.code == expected_code
    assert err.broker == "zerodha"

    assert message in str(err)

def test_classify_message_unknown_uses_fallback() -> None:
    err = classify_message("some novel error we haven't seen", broker="fyers")
    assert isinstance(err, InvalidOrderError)
    assert err.code == "UNKNOWN_ERROR"

def test_classify_message_respects_custom_fallback() -> None:
    err = classify_message(
        "unclassifiable",
        broker="upstox",
        fallback=AuthError,
        fallback_code="CUSTOM_FALLBACK",
    )
    assert isinstance(err, AuthError)
    assert err.code == "CUSTOM_FALLBACK"

def test_amo_not_supported_error_exists() -> None:
    """Smoke test — used by Zerodha adapter when AMO+MARKET is requested."""
    err = AmoNotSupportedError("x", code="AMO_NOT_SUPPORTED", broker="zerodha")
    assert isinstance(err, InvalidOrderError)
    assert err.code == "AMO_NOT_SUPPORTED"

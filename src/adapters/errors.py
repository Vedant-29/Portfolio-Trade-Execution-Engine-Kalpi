from __future__ import annotations

import re
from dataclasses import dataclass


class BrokerError(Exception):
    """Base for all broker-originated errors. Each adapter translates its
    SDK's exceptions into a subclass of this — the service layer catches
    only these types.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        broker: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.broker = broker

class AuthError(BrokerError):
    """401 / invalid credentials / expired token. Not retryable."""

class RateLimitError(BrokerError):
    """429 or broker-specific throttle signal. Retryable with backoff."""

class TransientBrokerError(BrokerError):
    """5xx / network blip. Retryable."""

class InvalidOrderError(BrokerError):
    """4xx from broker indicating the order itself is bad. NOT retryable."""

class InsufficientFundsError(InvalidOrderError):
    """The account's available margin is less than the order's required margin."""

class InvalidSymbolError(InvalidOrderError):
    """Broker does not recognize the trading symbol / exchange combo."""

class MarketClosedError(InvalidOrderError):
    """Order was rejected because the exchange is closed. Suggests AMO."""

class CircuitLimitError(InvalidOrderError):
    """Stock is at the upper/lower circuit — price can't move in this
    direction right now."""

class AmoNotSupportedError(InvalidOrderError):
    """AMO was requested in a combination the broker doesn't allow
    (e.g. Zerodha AMO + MARKET). Not retryable."""

@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    error: type[BrokerError]
    code: str

_COMMON_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(re.compile(r"insufficient\s+funds?", re.I), InsufficientFundsError, "INSUFFICIENT_FUNDS"),
    _Pattern(re.compile(r"required\s+margin", re.I), InsufficientFundsError, "INSUFFICIENT_FUNDS"),
    _Pattern(re.compile(r"available\s+margin\s+is\s+0", re.I), InsufficientFundsError, "INSUFFICIENT_FUNDS"),
    _Pattern(re.compile(r"market\s+is\s+closed", re.I), MarketClosedError, "MARKET_CLOSED"),
    _Pattern(re.compile(r"after\s+market\s+order", re.I), MarketClosedError, "MARKET_CLOSED"),
    _Pattern(re.compile(r"amo.*not.*allowed", re.I), AmoNotSupportedError, "AMO_NOT_SUPPORTED"),
    _Pattern(re.compile(r"upper\s+circuit", re.I), CircuitLimitError, "CIRCUIT_LIMIT_UPPER"),
    _Pattern(re.compile(r"lower\s+circuit", re.I), CircuitLimitError, "CIRCUIT_LIMIT_LOWER"),
    _Pattern(re.compile(r"circuit", re.I), CircuitLimitError, "CIRCUIT_LIMIT"),
    _Pattern(re.compile(r"(invalid|unknown|not\s+found)\s+(symbol|instrument)", re.I), InvalidSymbolError, "INVALID_SYMBOL"),
    _Pattern(re.compile(r"symbol.*not.*found", re.I), InvalidSymbolError, "INVALID_SYMBOL"),
    _Pattern(re.compile(r"(rate\s*limit|too\s+many\s+requests)", re.I), RateLimitError, "RATE_LIMIT"),
    _Pattern(re.compile(r"(token|session).*(expired|invalid)", re.I), AuthError, "AUTH_EXPIRED"),
    _Pattern(re.compile(r"(no\s+ips?\s+configured|ip\s+not\s+allowed)", re.I), AuthError, "IP_NOT_WHITELISTED"),
)

def classify_message(
    message: str,
    *,
    broker: str,
    fallback: type[BrokerError] = InvalidOrderError,
    fallback_code: str = "UNKNOWN_ERROR",
    extra_patterns: tuple[_Pattern, ...] = (),
) -> BrokerError:
    """Translate a broker's error text into a typed BrokerError.

    Each adapter calls this with its SDK's error message. Broker-specific
    patterns (if any) can be prepended via `extra_patterns`; otherwise the
    shared _COMMON_PATTERNS handle the universal cases.

    The concrete error class carries the original message so the frontend
    can still show it; the `code` field is what the UI uses to render a
    friendly label.
    """
    patterns = extra_patterns + _COMMON_PATTERNS
    for pat in patterns:
        if pat.regex.search(message):
            return pat.error(message, code=pat.code, broker=broker)
    return fallback(message, code=fallback_code, broker=broker)

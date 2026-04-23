"""Zerodha Kite Connect adapter.

Auth flow (auth_kind = "oauth_redirect"):
  1. User clicks "Connect Zerodha" → frontend redirects browser to
     https://kite.zerodha.com/connect/login?api_key=... (the login URL
     Kite exposes via `KiteConnect.login_url()`).
  2. After successful login, Kite redirects back to our registered
     Redirect URL with `?request_token=XXX&action=login&status=success`.
  3. We exchange that request_token for an access_token by calling
     `KiteConnect.generate_session(request_token, api_secret)`. Under the
     hood it POSTs to `api.kite.trade/session/token` with
     `checksum = SHA256(api_key + request_token + api_secret)`.

The SDK (`kiteconnect`) is official Zerodha code, MIT-licensed. We use it
to avoid re-implementing the checksum/session HTTP dance — it's a
security-sensitive step and the SDK handles token refresh and exception
mapping consistently.

Header quirk: Kite's REST API wants `Authorization: token api_key:access_token`.
The SDK handles this when you call `kite.set_access_token(...)` on a
KiteConnect instance, but for the header format we expose via
`authorization_header(session)` we pre-concat `api_key:access_token` into
`session.access_token` at auth time (so downstream code doesn't need to
know the api_key separately).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from kiteconnect import KiteConnect
from kiteconnect import exceptions as kex

from src.adapters.base import BrokerAdapter
from src.adapters.errors import (
    AmoNotSupportedError,
    AuthError,
    BrokerError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
    classify_message,
)
from src.adapters.zerodha.mapping import (
    action_to_kite,
    exchange_from_kite,
    exchange_to_kite,
    price_type_to_kite,
    product_to_kite,
)
from src.config import get_settings
from src.schemas import BrokerSession, Holding, OrderRequest, OrderResult, PriceType

_MARKET_PROTECTION_PCT = 5.0

def _translate_kite_exception(exc: Exception, *, context: str) -> BrokerError:
    """Map kiteconnect exceptions onto our error taxonomy.

    Exception *type* is a coarse signal; the *message* is where Kite puts
    specific info like "Insufficient funds", "No IPs configured",
    "Market is closed". We rely on the type for retry classification
    (network/rate-limit) but the message for user-facing labels.
    """
    msg = f"{context}: {exc}"
    if isinstance(exc, kex.NetworkException):
        return TransientBrokerError(msg, code="NETWORK", broker="zerodha")
    if isinstance(exc, kex.TokenException | kex.PermissionException):

        return classify_message(
            msg, broker="zerodha", fallback=AuthError, fallback_code="AUTH_FAILED"
        )
    if isinstance(
        exc,
        kex.InputException
        | kex.OrderException
        | kex.DataException
        | kex.GeneralException,
    ):
        return classify_message(
            msg,
            broker="zerodha",
            fallback=InvalidOrderError,
            fallback_code="ORDER_REJECTED",
        )
    return BrokerError(msg, code="UNKNOWN_ERROR", broker="zerodha")

class ZerodhaAdapter(BrokerAdapter):
    name = "zerodha"
    display_name = "Zerodha"
    auth_kind = "oauth_redirect"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.zerodha_api_key
        self._api_secret = api_secret or settings.zerodha_api_secret
        if not (self._api_key and self._api_secret):
            raise AuthError(
                "Zerodha adapter requires ZERODHA_API_KEY and ZERODHA_API_SECRET",
                broker="zerodha",
            )

    def build_login_url(self, redirect_uri: str, state: str) -> str:

        kite = KiteConnect(api_key=self._api_key)
        return f"{kite.login_url()}&state={state}"

    def exchange_code_for_session(self, params: Mapping[str, str]) -> BrokerSession:
        request_token = params.get("request_token")
        if not request_token:
            raise AuthError(
                "Zerodha callback missing `request_token`", broker="zerodha"
            )
        kite = KiteConnect(api_key=self._api_key)
        try:
            data = kite.generate_session(request_token, api_secret=self._api_secret)
        except kex.TokenException as exc:
            raise AuthError(
                f"Kite session exchange rejected: {exc}", broker="zerodha"
            ) from exc
        except Exception as exc:
            raise _translate_kite_exception(exc, context="generate_session") from exc

        access_token = data["access_token"]

        return BrokerSession(
            broker="zerodha",
            access_token=f"{self._api_key}:{access_token}",
            token_header_format="token {access_token}",
            user_id=data.get("user_id"),
            extras={
                "public_token": data.get("public_token"),
                "login_time": data.get("login_time").isoformat()
                if data.get("login_time")
                else None,
            },
        )

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {
            "Authorization": session.token_header_format.format(
                access_token=session.access_token
            ),
            "X-Kite-Version": "3",
        }

    def _client(self, session: BrokerSession) -> KiteConnect:
        """Build an authenticated KiteConnect for a given session.

        `session.access_token` is `api_key:raw_access_token` — the SDK
        just wants the raw access_token, so we strip the api_key prefix.
        """
        _, _, raw_token = session.access_token.partition(":")
        kite = KiteConnect(api_key=self._api_key)
        kite.set_access_token(raw_token)
        return kite

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:

        if req.amo and req.price_type is PriceType.MARKET:
            raise AmoNotSupportedError(
                "Zerodha AMO requires a LIMIT price. MARKET orders cannot "
                "be queued after-market via Kite.",
                code="AMO_NOT_SUPPORTED",
                broker="zerodha",
            )

        kite = self._client(session)
        kwargs: dict = {
            "variety": KiteConnect.VARIETY_AMO if req.amo else KiteConnect.VARIETY_REGULAR,
            "exchange": exchange_to_kite(req.exchange),
            "tradingsymbol": req.symbol,
            "transaction_type": action_to_kite(req.action),
            "quantity": req.quantity,
            "product": product_to_kite(req.product),
            "order_type": price_type_to_kite(req.price_type),
        }
        if req.price is not None:
            kwargs["price"] = float(req.price)

        if req.price_type is PriceType.MARKET and not req.amo:
            kwargs["market_protection"] = _MARKET_PROTECTION_PCT
        try:
            broker_order_id = kite.place_order(**kwargs)
        except Exception as exc:
            err = _translate_kite_exception(exc, context="place_order")

            if isinstance(err, TransientBrokerError | RateLimitError):
                raise err from exc
            return OrderResult.failed(
                req,
                code=err.code or "ORDER_REJECTED",
                message=str(err),
            )
        return OrderResult.placed(req, broker_order_id=str(broker_order_id))

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        kite = self._client(session)
        try:
            kite.cancel_order(
                variety=KiteConnect.VARIETY_REGULAR, order_id=broker_order_id
            )
        except Exception as exc:
            raise _translate_kite_exception(exc, context="cancel_order") from exc

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        kite = self._client(session)
        try:
            history = kite.order_history(broker_order_id)
        except Exception as exc:
            raise _translate_kite_exception(exc, context="order_history") from exc
        if not history:
            raise BrokerError(
                f"No history for order_id={broker_order_id}", broker="zerodha"
            )
        latest = history[-1]
        req = OrderRequest(
            symbol=latest["tradingsymbol"],
            exchange=exchange_from_kite(latest["exchange"]),
            action=latest["transaction_type"],
            quantity=latest["quantity"],
            product=latest["product"],
            price_type=latest["order_type"],
            price=Decimal(str(latest["price"])) if latest.get("price") else None,
        )
        status = latest.get("status", "")
        if status in {"REJECTED", "CANCELLED"}:
            return OrderResult.failed(
                req,
                code=f"KITE_STATUS_{status}",
                message=latest.get("status_message") or status,
            )
        return OrderResult.placed(req, broker_order_id=broker_order_id)

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        kite = self._client(session)
        try:
            rows = kite.holdings()
        except Exception as exc:
            raise _translate_kite_exception(exc, context="holdings") from exc
        result: list[Holding] = []
        for r in rows:
            qty = int(r.get("quantity", 0))
            if qty <= 0:
                continue
            result.append(
                Holding(
                    symbol=r["tradingsymbol"],
                    exchange=exchange_from_kite(r["exchange"]),
                    quantity=qty,
                    average_price=Decimal(str(r["average_price"]))
                    if r.get("average_price") is not None
                    else None,
                )
            )
        return result

    def _ratelimit_guard(self, exc: Exception) -> None:
        """Kite uses NetworkException for transient issues and doesn't
        expose a typed 429 — callers should retry Transient; if we see
        message containing 'too many requests' we upgrade to RateLimitError."""
        if "too many requests" in str(exc).lower():
            raise RateLimitError(str(exc), broker="zerodha") from exc

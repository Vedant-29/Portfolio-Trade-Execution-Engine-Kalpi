"""Groww Trading API adapter.

Auth flow (auth_kind = "api_key_only"):
  Unlike OAuth brokers there is NO user-facing redirect or form.
  The user configures `GROWW_API_KEY` + `GROWW_API_SECRET` once in
  `.env`. When they click "Connect Groww", we call the SDK's
  `GrowwAPI.get_access_token(api_key, secret=api_secret)` which
  performs a server-to-server POST to
  `api.groww.in/v1/token/api/access` with
  `checksum = SHA256(api_secret + timestamp)`. The returned token
  is valid for ~24 hours.

Why `api_key_only` is a distinct flavor:
  Groww pre-requires that the user has generated their API secret
  from the Groww app itself (a one-time, out-of-band step). After
  that, authentication is non-interactive from our side. The ABC's
  `authenticate_from_env()` captures exactly this case without
  forcing Groww into the OAuth redirect dance.
"""

from __future__ import annotations

from decimal import Decimal

from growwapi import GrowwAPI

from src.adapters.base import BrokerAdapter
from src.adapters.errors import (
    AmoNotSupportedError,
    AuthError,
    BrokerError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
)
from src.adapters.groww.mapping import (
    EXCHANGE_MAP,
    PRICE_TYPE_MAP,
    PRODUCT_MAP,
    segment_for,
)
from src.config import get_settings
from src.schemas import (
    Action,
    BrokerSession,
    Exchange,
    Holding,
    OrderRequest,
    OrderResult,
)


def _translate(exc: Exception, *, context: str) -> BrokerError:
    msg = f"{context}: {exc}"
    lowered = str(exc).lower()
    if any(k in lowered for k in ("unauthor", "invalid token", "expired", "401", "403")):
        return AuthError(msg, broker="groww")
    if "429" in lowered or "rate" in lowered:
        return RateLimitError(msg, broker="groww")
    if any(k in lowered for k in ("timeout", "connection", "500", "502", "503", "504")):
        return TransientBrokerError(msg, broker="groww")
    return BrokerError(msg, broker="groww")

class GrowwAdapter(BrokerAdapter):
    name = "groww"
    display_name = "Groww"
    auth_kind = "api_key_only"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.groww_api_key
        self._api_secret = api_secret or settings.groww_api_secret
        if not (self._api_key and self._api_secret):
            raise AuthError(
                "Groww adapter requires GROWW_API_KEY and GROWW_API_SECRET",
                broker="groww",
            )

    def authenticate_from_env(self) -> BrokerSession:
        try:
            result = GrowwAPI.get_access_token(
                api_key=self._api_key, secret=self._api_secret
            )
        except Exception as exc:
            raise AuthError(
                f"Groww token exchange failed: {exc}", broker="groww"
            ) from exc
        if not isinstance(result, dict) or "token" not in result:
            raise AuthError(
                f"Unexpected Groww auth response: {str(result)[:200]}",
                broker="groww",
            )
        return BrokerSession(
            broker="groww",
            access_token=result["token"],
            token_header_format="Bearer {access_token}",
        )

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {
            "Authorization": session.token_header_format.format(
                access_token=session.access_token
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _client(self, session: BrokerSession) -> GrowwAPI:
        return GrowwAPI(token=session.access_token)

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:

        if req.amo:
            raise AmoNotSupportedError(
                "Groww's Python SDK does not expose an AMO parameter. "
                "Place the order during market hours (9:15–15:30 IST) or "
                "use another broker for after-market queuing.",
                code="AMO_NOT_SUPPORTED",
                broker="groww",
            )
        client = self._client(session)
        try:
            resp = client.place_order(
                validity="DAY",
                exchange=EXCHANGE_MAP[req.exchange],
                order_type=PRICE_TYPE_MAP[req.price_type],
                product=PRODUCT_MAP[req.product],
                quantity=req.quantity,
                segment=segment_for(req.exchange),
                trading_symbol=req.symbol,
                transaction_type=Action(req.action).value,
                price=float(req.price) if req.price is not None else 0.0,
            )
        except Exception as exc:
            err = _translate(exc, context="place_order")
            if isinstance(err, AuthError | RateLimitError | TransientBrokerError):
                raise err from exc
            return OrderResult.failed(
                req, code="GROWW_REJECTED", message=str(err)
            )
        if not isinstance(resp, dict):
            return OrderResult.failed(
                req, code="GROWW_BAD_RESP", message=str(resp)[:200]
            )
        order_id = resp.get("groww_order_id") or resp.get("orderId")
        if not order_id:
            msg = resp.get("message") or resp.get("error") or "no order_id"
            return OrderResult.failed(
                req, code="GROWW_REJECTED", message=str(msg)
            )
        return OrderResult.placed(req, broker_order_id=str(order_id))

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        client = self._client(session)
        try:
            resp = client.cancel_order(
                groww_order_id=broker_order_id,
                segment=GrowwAPI.SEGMENT_CASH,
            )
        except Exception as exc:
            raise _translate(exc, context="cancel_order") from exc
        if isinstance(resp, dict) and resp.get("status") == "FAILED":
            raise InvalidOrderError(
                resp.get("message", "cancel failed"), broker="groww"
            )

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        client = self._client(session)
        try:
            resp = client.get_order_status(
                segment=GrowwAPI.SEGMENT_CASH, groww_order_id=broker_order_id
            )
        except Exception as exc:
            raise _translate(exc, context="get_order_status") from exc
        if not isinstance(resp, dict):
            raise BrokerError(
                f"Unexpected status response: {str(resp)[:200]}", broker="groww"
            )
        data = resp.get("data") or resp
        req = OrderRequest(
            symbol=data.get("trading_symbol", "UNKNOWN"),
            exchange=Exchange(data.get("exchange", "NSE")),
            action=Action(data.get("transaction_type", "BUY")),
            quantity=int(data.get("quantity", 0)) or 1,
        )
        status = (data.get("order_status") or data.get("status") or "").upper()
        if status in {"REJECTED", "CANCELLED", "FAILED"}:
            return OrderResult.failed(
                req,
                code=f"GROWW_STATUS_{status}",
                message=data.get("message") or status,
            )
        return OrderResult.placed(req, broker_order_id=broker_order_id)

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        client = self._client(session)
        try:
            resp = client.get_holdings_for_user()
        except Exception as exc:
            raise _translate(exc, context="get_holdings") from exc
        rows = (
            resp.get("data", {}).get("holdings", [])
            if isinstance(resp, dict)
            else []
        )
        out: list[Holding] = []
        for row in rows:
            qty = int(row.get("quantity", 0) or 0)
            if qty <= 0:
                continue
            out.append(
                Holding(
                    symbol=row.get("trading_symbol", ""),
                    exchange=Exchange(row.get("exchange", "NSE")),
                    quantity=qty,
                    average_price=Decimal(str(row["average_price"]))
                    if row.get("average_price") is not None
                    else None,
                )
            )
        return out

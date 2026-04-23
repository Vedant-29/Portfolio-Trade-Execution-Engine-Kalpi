"""Paytm Money adapter.

Auth flow (auth_kind = "oauth_redirect"):
  1. Frontend redirects browser to
     https://login.paytmmoney.com/merchant-login
       ?apiKey=...&state=...
  2. Paytm redirects back with `?request_token=XXX&state=...`.
  3. We POST to https://developer.paytmmoney.com/accounts/v2/gettoken
     with JSON {api_key, api_secret_key, request_token}. The response
     returns `access_token` + `public_access_token` (separate WebSocket
     bearer) + `read_access_token`.

Paytm does not ship an official Python SDK as of 2025, so this
adapter uses raw httpx against their documented REST endpoints.
Endpoints + response shapes sourced from Paytm's developer docs and
cross-checked against OpenAlgo's reference (github.com/marketcalls/
openalgo/tree/main/broker/paytm) — code not copied.

Symbol lookup:
  Paytm's place-order requires a numeric `security_id` (scrip token),
  not a plain tradingsymbol. In production we'd keep a cached
  symbol → security_id map. For the scaffold we accept the symbol
  and raise if a mapping isn't provided — a placeholder to fill in
  when testing live.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import httpx

from src.adapters.base import BrokerAdapter
from src.adapters.errors import (
    AuthError,
    BrokerError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
    classify_message,
)
from src.adapters.paytm.mapping import (
    ACTION_MAP,
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

_BASE_URL = "https://developer.paytmmoney.com"
_LOGIN_BASE = "https://login.paytmmoney.com"


class PaytmAdapter(BrokerAdapter):
    name = "paytm"
    display_name = "Paytm Money"
    auth_kind = "oauth_redirect"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.paytm_api_key
        self._api_secret = api_secret or settings.paytm_api_secret
        if not (self._api_key and self._api_secret):
            raise AuthError(
                "Paytm Money adapter requires PAYTM_API_KEY and PAYTM_API_SECRET",
                broker="paytm",
            )
        self._security_id_cache: dict[tuple[str, Exchange], str] = {}

    def build_login_url(self, redirect_uri: str, state: str) -> str:
        del redirect_uri
        return (
            f"{_LOGIN_BASE}/merchant-login"
            f"?apiKey={self._api_key}&state={state}"
        )

    def exchange_code_for_session(self, params: Mapping[str, str]) -> BrokerSession:
        request_token = params.get("request_token") or params.get("code")
        if not request_token:
            raise AuthError(
                "Paytm Money callback missing `request_token`", broker="paytm"
            )
        body = {
            "api_key": self._api_key,
            "api_secret_key": self._api_secret,
            "request_token": request_token,
        }
        try:
            resp = httpx.post(
                f"{_BASE_URL}/accounts/v2/gettoken",
                json=body,
                timeout=10.0,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise TransientBrokerError(
                f"Paytm token exchange network error: {exc}", broker="paytm"
            ) from exc
        if resp.status_code != 200:
            raise classify_message(
                f"Paytm token exchange HTTP {resp.status_code}: {resp.text[:200]}",
                broker="paytm",
                fallback=AuthError,
                fallback_code="AUTH_FAILED",
            )
        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise AuthError(
                f"Paytm token response missing access_token: {str(data)[:200]}",
                broker="paytm",
            )
        return BrokerSession(
            broker="paytm",
            access_token=access_token,
            token_header_format="Bearer {access_token}",
            feed_token=data.get("public_access_token"),
            user_id=data.get("user_id"),
            extras={
                "read_access_token": data.get("read_access_token"),
            },
        )

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {
            "x-jwt-token": session.access_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _security_id(self, symbol: str, exchange: Exchange) -> str:
        """Resolve (symbol, exchange) to Paytm's numeric security_id.

        Paytm publishes a scrip-master CSV at
        https://developer.paytmmoney.com/docs/api/scrip-master (gated
        behind login). The production path is: download the CSV at
        adapter startup, populate this cache. For the scaffold we
        fail loudly so a user enabling Paytm knows to wire this up.
        """
        cached = self._security_id_cache.get((symbol, exchange))
        if cached:
            return cached
        raise InvalidOrderError(
            f"Paytm security_id lookup not implemented yet for "
            f"{symbol}/{exchange.value}. See `_security_id` in "
            "paytm/adapter.py — needs the scrip-master CSV loaded at "
            "startup.",
            broker="paytm",
        )

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        security_id = self._security_id(req.symbol, req.exchange)
        body = {
            "security_id": security_id,
            "exchange": EXCHANGE_MAP[req.exchange],
            "txn_type": ACTION_MAP[req.action],
            "order_type": PRICE_TYPE_MAP[req.price_type],
            "quantity": req.quantity,
            "product": PRODUCT_MAP[req.product],
            "price": str(req.price) if req.price is not None else "0",
            "validity": "DAY",
            "segment": segment_for(req.exchange),
            "source": "API",
        }
        if req.amo:
            body["off_mkt_flag"] = True
        try:
            resp = httpx.post(
                f"{_BASE_URL}/orders/v1/place/regular",
                json=body,
                headers=self.authorization_header(session),
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise TransientBrokerError(
                f"Paytm place_order network error: {exc}", broker="paytm"
            ) from exc
        if resp.status_code >= 500:
            raise TransientBrokerError(
                f"Paytm server error {resp.status_code}: {resp.text[:200]}",
                broker="paytm",
            )
        if resp.status_code == 429:
            raise RateLimitError(
                f"Paytm rate limit: {resp.text[:200]}", broker="paytm"
            )
        if resp.status_code == 401:
            raise AuthError(
                f"Paytm auth rejected: {resp.text[:200]}", broker="paytm"
            )
        if resp.status_code >= 400:
            return OrderResult.failed(
                req,
                code="PAYTM_REJECTED",
                message=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )
        data = resp.json()
        order_id = (
            (data.get("data") or {}).get("order_no")
            or data.get("order_no")
            or data.get("order_id")
        )
        if not order_id:
            return OrderResult.failed(
                req,
                code="PAYTM_NO_ORDER_ID",
                message=f"Response missing order_no: {str(data)[:200]}",
            )
        return OrderResult.placed(req, broker_order_id=str(order_id))

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        try:
            resp = httpx.post(
                f"{_BASE_URL}/orders/v1/cancel/regular",
                json={"order_no": broker_order_id, "source": "API"},
                headers=self.authorization_header(session),
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise TransientBrokerError(
                f"Paytm cancel_order network error: {exc}", broker="paytm"
            ) from exc
        if resp.status_code >= 400:
            raise BrokerError(
                f"Paytm cancel rejected HTTP {resp.status_code}: {resp.text[:200]}",
                broker="paytm",
            )

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        try:
            resp = httpx.get(
                f"{_BASE_URL}/orders/v1/status",
                params={"order_no": broker_order_id},
                headers=self.authorization_header(session),
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise TransientBrokerError(
                f"Paytm order status network error: {exc}", broker="paytm"
            ) from exc
        if resp.status_code >= 400:
            raise BrokerError(
                f"Paytm status HTTP {resp.status_code}: {resp.text[:200]}",
                broker="paytm",
            )
        data = (resp.json() or {}).get("data") or {}
        req = OrderRequest(
            symbol=data.get("display_name", "UNKNOWN"),
            exchange=Exchange(data.get("exchange", "NSE")),
            action=Action.BUY if data.get("txn_type") == "B" else Action.SELL,
            quantity=int(data.get("quantity", 0)) or 1,
        )
        status = (data.get("status") or "").upper()
        if status in {"REJECTED", "CANCELLED", "FAILED"}:
            return OrderResult.failed(
                req,
                code=f"PAYTM_STATUS_{status}",
                message=data.get("status_message") or status,
            )
        return OrderResult.placed(req, broker_order_id=broker_order_id)

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        try:
            resp = httpx.get(
                f"{_BASE_URL}/holdings/v1/get-user-holdings-data",
                headers=self.authorization_header(session),
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise TransientBrokerError(
                f"Paytm holdings network error: {exc}", broker="paytm"
            ) from exc
        if resp.status_code >= 400:
            raise BrokerError(
                f"Paytm holdings HTTP {resp.status_code}: {resp.text[:200]}",
                broker="paytm",
            )
        rows = ((resp.json() or {}).get("data") or {}).get("results") or []
        out: list[Holding] = []
        for row in rows:
            qty = int(row.get("quantity", 0) or 0)
            if qty <= 0:
                continue
            avg = row.get("cost_price")
            out.append(
                Holding(
                    symbol=row.get("display_name", ""),
                    exchange=Exchange(row.get("exchange", "NSE")),
                    quantity=qty,
                    average_price=Decimal(str(avg)) if avg is not None else None,
                )
            )
        return out

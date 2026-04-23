"""AngelOne SmartAPI adapter.

Auth flow (auth_kind = "credentials_form"):
  Unlike Zerodha/Upstox there is NO OAuth redirect. The user types
  their Client ID, MPIN (PIN), and TOTP directly into a form WE render.
  We then POST to AngelOne's `loginByPassword` endpoint via the
  `smartapi-python` SDK (`SmartConnect.generateSession(client, pin, totp)`)
  which returns a JWT access token + a separate `feedToken` for the
  WebSocket feed. We store both; `feedToken` lives in `session.feed_token`.

Optional: if `ANGELONE_TOTP_SECRET` is set in .env, we can generate the
TOTP server-side via `pyotp`, which lets us offer a one-click "Connect"
button in addition to the form. For the assignment we keep the primary
path form-based (matches the spec of credentials_form flow).

Symbol tokens:
  AngelOne requires a numeric symbol_token per instrument. The SDK's
  `searchScrip(exchange, symbol)` returns it. We cache results in-process.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pyotp
from SmartApi import SmartConnect

from src.adapters.angelone.mapping import (
    EXCHANGE_MAP,
    PRICE_TYPE_MAP,
    PRODUCT_MAP,
)
from src.adapters.base import BrokerAdapter, FieldSpec
from src.adapters.errors import (
    AuthError,
    BrokerError,
    InvalidOrderError,
    TransientBrokerError,
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


class AngelOneAdapter(BrokerAdapter):
    name = "angelone"
    display_name = "AngelOne"
    auth_kind = "credentials_form"

    def __init__(
        self,
        api_key: str | None = None,
        totp_secret: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.angelone_api_key

        self._totp_secret = totp_secret or settings.angelone_totp_secret
        if not self._api_key:
            raise AuthError(
                "AngelOne adapter requires ANGELONE_API_KEY", broker="angelone"
            )
        self._symbol_token_cache: dict[tuple[str, Exchange], str] = {}

    def credential_fields(self) -> list[FieldSpec]:
        fields = [
            FieldSpec(name="client_id", label="Client ID", type="text"),
            FieldSpec(name="pin", label="PIN", type="password"),
        ]
        if not self._totp_secret:
            fields.append(
                FieldSpec(
                    name="totp",
                    label="6-digit TOTP",
                    type="text",
                    pattern="[0-9]{6}",
                    max_length=6,
                    hint="From your authenticator app",
                )
            )
        return fields

    def authenticate_with_credentials(self, **fields: str) -> BrokerSession:
        client_id = fields.get("client_id")
        pin = fields.get("pin")
        totp = fields.get("totp")
        if not (client_id and pin):
            raise AuthError("client_id and pin are required", broker="angelone")
        if not totp:
            if not self._totp_secret:
                raise AuthError(
                    "TOTP required — provide it in the form or set "
                    "ANGELONE_TOTP_SECRET to generate it server-side",
                    broker="angelone",
                )
            totp = pyotp.TOTP(self._totp_secret).now()

        sc = SmartConnect(api_key=self._api_key)
        try:
            data = sc.generateSession(clientCode=client_id, password=pin, totp=totp)
        except Exception as exc:
            raise AuthError(
                f"AngelOne login failed: {exc}", broker="angelone"
            ) from exc

        if not data or not data.get("status"):
            raise AuthError(
                f"AngelOne login rejected: {data.get('message') if data else 'no response'}",
                broker="angelone",
            )
        inner = data["data"]
        return BrokerSession(
            broker="angelone",
            access_token=inner["jwtToken"],
            token_header_format="Bearer {access_token}",
            feed_token=inner.get("feedToken"),
            refresh_token=inner.get("refreshToken"),
            user_id=client_id,
            extras={"api_key": self._api_key},
        )

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {
            "Authorization": session.token_header_format.format(
                access_token=session.access_token
            ),
            "X-PrivateKey": self._api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _client(self, session: BrokerSession) -> SmartConnect:
        sc = SmartConnect(api_key=self._api_key)

        sc.setAccessToken(session.access_token)
        if session.refresh_token:
            sc.setRefreshToken(session.refresh_token)
        if session.feed_token:
            sc.setFeedToken(session.feed_token)
        sc.setUserId(session.user_id or "")
        return sc

    def _symbol_token(
        self, session: BrokerSession, symbol: str, exchange: Exchange
    ) -> str:
        cached = self._symbol_token_cache.get((symbol, exchange))
        if cached:
            return cached
        sc = self._client(session)
        try:
            resp = sc.searchScrip(exchange=EXCHANGE_MAP[exchange], searchtext=symbol)
        except Exception as exc:
            raise TransientBrokerError(
                f"searchScrip failed: {exc}", broker="angelone"
            ) from exc
        for row in resp.get("data", []) or []:
            if row.get("tradingsymbol", "").upper().startswith(symbol.upper()):
                token = row["symboltoken"]
                self._symbol_token_cache[(symbol, exchange)] = token
                return token
        raise InvalidOrderError(
            f"AngelOne symbol_token not found for {symbol}/{exchange.value}",
            broker="angelone",
        )

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        sc = self._client(session)
        symbol_token = self._symbol_token(session, req.symbol, req.exchange)
        params = {
            "variety": "AMO" if req.amo else "NORMAL",
            "tradingsymbol": req.symbol,
            "symboltoken": symbol_token,
            "transactiontype": Action(req.action).value,
            "exchange": EXCHANGE_MAP[req.exchange],
            "ordertype": PRICE_TYPE_MAP[req.price_type],
            "producttype": PRODUCT_MAP[req.product],
            "duration": "DAY",
            "price": str(req.price) if req.price is not None else "0",
            "quantity": str(req.quantity),
        }
        try:
            resp = sc.placeOrder(params)
        except Exception as exc:

            msg = str(exc).lower()
            if "timeout" in msg or "connection" in msg:
                raise TransientBrokerError(str(exc), broker="angelone") from exc
            raise BrokerError(str(exc), broker="angelone") from exc

        order_id = None
        if isinstance(resp, str):
            order_id = resp
        elif isinstance(resp, dict):
            if resp.get("status") is False:
                return OrderResult.failed(
                    req,
                    code="ANGELONE_REJECTED",
                    message=resp.get("message", "order rejected"),
                )
            inner = resp.get("data")
            if isinstance(inner, dict):
                order_id = inner.get("orderid") or inner.get("order_id")
            elif isinstance(inner, str):
                order_id = inner
        if not order_id:
            return OrderResult.failed(
                req,
                code="ANGELONE_NO_ORDER_ID",
                message=f"Unexpected placeOrder response: {json.dumps(resp, default=str)[:200]}",
            )
        return OrderResult.placed(req, broker_order_id=str(order_id))

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        sc = self._client(session)
        try:
            resp = sc.cancelOrder(order_id=broker_order_id, variety="NORMAL")
        except Exception as exc:
            raise BrokerError(str(exc), broker="angelone") from exc
        if isinstance(resp, dict) and resp.get("status") is False:
            raise BrokerError(
                resp.get("message", "cancel rejected"), broker="angelone"
            )

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        sc = self._client(session)
        try:
            resp = sc.individual_order_details(qParam=broker_order_id)
        except Exception as exc:
            raise BrokerError(str(exc), broker="angelone") from exc
        if isinstance(resp, dict) and not resp.get("status"):
            raise BrokerError(
                resp.get("message", "lookup failed"), broker="angelone"
            )
        inner = (resp or {}).get("data") if isinstance(resp, dict) else None
        if not inner:
            raise BrokerError(
                f"No order details for {broker_order_id}", broker="angelone"
            )
        req = OrderRequest(
            symbol=inner.get("tradingsymbol", "UNKNOWN"),
            exchange=Exchange(inner.get("exchange", "NSE")),
            action=Action(inner.get("transactiontype", "BUY")),
            quantity=int(inner.get("quantity", 0)) or 1,
        )
        status = (inner.get("status") or "").upper()
        if status in {"REJECTED", "CANCELLED"}:
            return OrderResult.failed(
                req,
                code=f"ANGELONE_STATUS_{status}",
                message=inner.get("text") or status,
            )
        return OrderResult.placed(req, broker_order_id=broker_order_id)

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        sc = self._client(session)
        try:
            resp = sc.holding()
        except Exception as exc:
            raise BrokerError(str(exc), broker="angelone") from exc
        rows = (resp or {}).get("data") if isinstance(resp, dict) else None
        out: list[Holding] = []
        for row in rows or []:
            qty = int(row.get("quantity", 0) or 0)
            if qty <= 0:
                continue
            out.append(
                Holding(
                    symbol=row.get("tradingsymbol", ""),
                    exchange=Exchange(row.get("exchange", "NSE")),
                    quantity=qty,
                    average_price=Decimal(str(row["averageprice"]))
                    if row.get("averageprice") is not None
                    else None,
                )
            )
        return out

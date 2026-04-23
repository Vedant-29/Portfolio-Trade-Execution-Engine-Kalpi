"""Upstox adapter.

Auth flow (auth_kind = "oauth_redirect"):
  1. Frontend redirects browser to
     https://api.upstox.com/v2/login/authorization/dialog
       ?response_type=code&client_id=API_KEY&redirect_uri=...&state=...
  2. Upstox redirects back with `?code=XXX&state=...`.
  3. We exchange via `LoginApi.token(api_version, ...)` which POSTs
     to `/v2/login/authorization/token` with a standard OAuth2
     `authorization_code` grant — no checksum needed.

Instrument-token wart:
  Upstox `place_order` requires an `instrument_token` (e.g. `NSE_EQ|INE002A01018`)
  not a plain symbol. We resolve this via `InstrumentsApi.search_instrument`
  on demand and cache results in-process. For a production system we'd
  pre-load the full instrument master on boot.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from upstox_client import (
    ApiClient,
    Configuration,
    InstrumentsApi,
    LoginApi,
    OrderApi,
    PlaceOrderRequest,
    PortfolioApi,
)
from upstox_client.rest import ApiException

from src.adapters.base import BrokerAdapter
from src.adapters.errors import (
    AuthError,
    BrokerError,
    InvalidOrderError,
    RateLimitError,
    TransientBrokerError,
)
from src.adapters.upstox.mapping import (
    action_to_upstox,
    exchange_segment,
    price_type_to_upstox,
    product_to_upstox,
)
from src.config import get_settings
from src.schemas import BrokerSession, Exchange, Holding, OrderRequest, OrderResult

_API_VERSION = "2.0"

def _translate(exc: ApiException, *, context: str) -> BrokerError:
    status = exc.status or 0
    msg = f"{context}: HTTP {status} {exc.reason} — {exc.body}"
    if status in (401, 403):
        return AuthError(msg, code=f"HTTP_{status}", broker="upstox")
    if status == 429:
        return RateLimitError(msg, code="HTTP_429", broker="upstox")
    if 500 <= status < 600:
        return TransientBrokerError(msg, code=f"HTTP_{status}", broker="upstox")
    if 400 <= status < 500:
        return InvalidOrderError(msg, code=f"HTTP_{status}", broker="upstox")
    return BrokerError(msg, broker="upstox")

class UpstoxAdapter(BrokerAdapter):
    name = "upstox"
    display_name = "Upstox"
    auth_kind = "oauth_redirect"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.upstox_api_key
        self._api_secret = api_secret or settings.upstox_api_secret
        self._redirect_uri = redirect_uri or (
            f"{settings.public_base_url}/auth/upstox/callback"
        )
        if not (self._api_key and self._api_secret):
            raise AuthError(
                "Upstox adapter requires UPSTOX_API_KEY and UPSTOX_API_SECRET",
                broker="upstox",
            )

        self._instrument_cache: dict[tuple[str, Exchange], str] = {}

    def build_login_url(self, redirect_uri: str, state: str) -> str:

        return (
            "https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={self._api_key}"
            f"&redirect_uri={redirect_uri}&state={state}"
        )

    def exchange_code_for_session(self, params: Mapping[str, str]) -> BrokerSession:
        code = params.get("code")
        if not code:
            raise AuthError("Upstox callback missing `code`", broker="upstox")
        api = LoginApi(ApiClient(Configuration()))
        try:
            data = api.token(
                api_version=_API_VERSION,
                code=code,
                client_id=self._api_key,
                client_secret=self._api_secret,
                redirect_uri=self._redirect_uri,
                grant_type="authorization_code",
            )
        except ApiException as exc:
            raise _translate(exc, context="Upstox token exchange") from exc

        return BrokerSession(
            broker="upstox",
            access_token=data.access_token,
            token_header_format="Bearer {access_token}",
            user_id=getattr(data, "user_id", None),
        )

    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        return {
            "Authorization": session.token_header_format.format(
                access_token=session.access_token
            ),
            "Accept": "application/json",
        }

    def _client(self, session: BrokerSession) -> ApiClient:
        cfg = Configuration()
        cfg.access_token = session.access_token
        return ApiClient(cfg)

    def _instrument_key(
        self, session: BrokerSession, symbol: str, exchange: Exchange
    ) -> str:
        cached = self._instrument_cache.get((symbol, exchange))
        if cached:
            return cached
        api = InstrumentsApi(self._client(session))
        try:
            results = api.search_instrument(
                api_version=_API_VERSION, query=symbol, exchange=exchange_segment(exchange)
            )
        except ApiException as exc:
            raise _translate(exc, context=f"search_instrument({symbol})") from exc
        data = results.data or []
        for row in data:
            if (
                getattr(row, "trading_symbol", "").upper() == symbol.upper()
                and getattr(row, "exchange", "") == exchange_segment(exchange)
            ):
                key = row.instrument_key
                self._instrument_cache[(symbol, exchange)] = key
                return key
        raise InvalidOrderError(
            f"No Upstox instrument for {symbol} on {exchange.value}", broker="upstox"
        )

    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        instrument_key = self._instrument_key(session, req.symbol, req.exchange)
        body = PlaceOrderRequest(
            quantity=req.quantity,
            product=product_to_upstox(req.product),
            validity="DAY",
            price=float(req.price) if req.price is not None else 0.0,
            instrument_token=instrument_key,
            order_type=price_type_to_upstox(req.price_type),
            transaction_type=action_to_upstox(req.action),
            disclosed_quantity=0,
            is_amo=req.amo,
        )
        api = OrderApi(self._client(session))
        try:
            resp = api.place_order(body=body, api_version=_API_VERSION)
        except ApiException as exc:
            err = _translate(exc, context="place_order")
            if isinstance(err, InvalidOrderError):
                return OrderResult.failed(
                    req, code=err.code or "UPSTOX_INVALID", message=str(err)
                )
            raise err from exc
        order_id = getattr(resp.data, "order_id", None) if resp.data else None
        if not order_id:
            return OrderResult.failed(
                req, code="UPSTOX_NO_ORDER_ID", message="Response missing order_id"
            )
        return OrderResult.placed(req, broker_order_id=str(order_id))

    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None:
        api = OrderApi(self._client(session))
        try:
            api.cancel_order(order_id=broker_order_id, api_version=_API_VERSION)
        except ApiException as exc:
            raise _translate(exc, context="cancel_order") from exc

    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult:
        api = OrderApi(self._client(session))
        try:
            resp = api.get_order_details(
                api_version=_API_VERSION, order_id=broker_order_id
            )
        except ApiException as exc:
            raise _translate(exc, context="get_order_details") from exc
        d = resp.data
        req = OrderRequest(
            symbol=getattr(d, "trading_symbol", "UNKNOWN"),
            exchange=Exchange.NSE,
            action=getattr(d, "transaction_type", "BUY"),
            quantity=int(getattr(d, "quantity", 0)) or 1,
        )
        status = (getattr(d, "status", "") or "").upper()
        if status in {"REJECTED", "CANCELLED"}:
            return OrderResult.failed(
                req,
                code=f"UPSTOX_STATUS_{status}",
                message=getattr(d, "status_message", status) or status,
            )
        return OrderResult.placed(req, broker_order_id=broker_order_id)

    def get_holdings(self, session: BrokerSession) -> list[Holding]:
        api = PortfolioApi(self._client(session))
        try:
            resp = api.get_holdings(api_version=_API_VERSION)
        except ApiException as exc:
            raise _translate(exc, context="get_holdings") from exc
        out: list[Holding] = []
        for row in resp.data or []:
            qty = int(getattr(row, "quantity", 0) or 0)
            if qty <= 0:
                continue

            raw_exchange = getattr(row, "exchange", "") or ""
            exchange = Exchange.BSE if raw_exchange.startswith("BSE") else Exchange.NSE
            avg = getattr(row, "average_price", None)
            out.append(
                Holding(
                    symbol=getattr(row, "trading_symbol", ""),
                    exchange=exchange,
                    quantity=qty,
                    average_price=Decimal(str(avg)) if avg is not None else None,
                )
            )
        return out

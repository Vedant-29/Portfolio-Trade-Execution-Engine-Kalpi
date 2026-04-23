"""Canonical ↔ Fyers v3 field translation.

Fyers uses numeric codes for side/order_type (e.g. BUY=1, SELL=-1,
MARKET=2, LIMIT=1) which we translate from our canonical enums.
"""

from __future__ import annotations

from src.schemas import Action, Exchange, PriceType, ProductType

ACTION_CODE = {Action.BUY: 1, Action.SELL: -1}

PRICE_TYPE_CODE = {PriceType.MARKET: 2, PriceType.LIMIT: 1}

PRODUCT_CODE = {
    ProductType.CNC: "CNC",
    ProductType.MIS: "INTRADAY",
}

_EXCHANGE_PREFIX = {
    Exchange.NSE: "NSE",
    Exchange.BSE: "BSE",
}


def fyers_symbol(symbol: str, exchange: Exchange) -> str:
    """Construct a Fyers v3 symbol string: e.g. 'NSE:RELIANCE-EQ'."""
    return f"{_EXCHANGE_PREFIX[exchange]}:{symbol}-EQ"

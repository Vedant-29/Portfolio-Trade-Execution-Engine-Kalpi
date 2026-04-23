"""Canonical ↔ AngelOne SmartAPI field translation.

AngelOne uses long English words on the wire (DELIVERY, INTRADAY,
MARKET, LIMIT) which we translate from our canonical enums.
"""

from __future__ import annotations

from src.schemas import Exchange, PriceType, ProductType

PRODUCT_MAP = {
    ProductType.CNC: "DELIVERY",
    ProductType.MIS: "INTRADAY",
}

PRICE_TYPE_MAP = {
    PriceType.MARKET: "MARKET",
    PriceType.LIMIT: "LIMIT",
}

EXCHANGE_MAP = {
    Exchange.NSE: "NSE",
    Exchange.BSE: "BSE",
}

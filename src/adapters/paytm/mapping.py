"""Canonical ↔ Paytm Money field translation.

Paytm uses single-character product codes and short order-type
abbreviations on the wire. Reference: OpenAlgo's paytm/mapping/
transform_data.py (learned from, not copied).
"""

from __future__ import annotations

from src.schemas import Action, Exchange, PriceType, ProductType

PRODUCT_MAP = {
    ProductType.CNC: "C",
    ProductType.MIS: "I",
}

PRICE_TYPE_MAP = {
    PriceType.MARKET: "MKT",
    PriceType.LIMIT: "LMT",
}

ACTION_MAP = {
    Action.BUY: "B",
    Action.SELL: "S",
}

EXCHANGE_MAP = {
    Exchange.NSE: "NSE",
    Exchange.BSE: "BSE",
}


def segment_for(exchange: Exchange) -> str:
    """Paytm groups instruments into segment codes. Cash equity is 'E'."""
    del exchange
    return "E"

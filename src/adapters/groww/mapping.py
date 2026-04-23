"""Canonical ↔ Groww field translation.

Groww's SDK already exposes matching constants (PRODUCT_CNC,
ORDER_TYPE_MARKET, etc.) so we just map our enums to those. The
segment helper is fixed at SEGMENT_CASH since we only support cash
equity; F&O and commodities are out of scope.
"""

from __future__ import annotations

from growwapi import GrowwAPI

from src.schemas import Exchange, PriceType, ProductType

PRODUCT_MAP = {
    ProductType.CNC: GrowwAPI.PRODUCT_CNC,
    ProductType.MIS: GrowwAPI.PRODUCT_MIS,
}

PRICE_TYPE_MAP = {
    PriceType.MARKET: GrowwAPI.ORDER_TYPE_MARKET,
    PriceType.LIMIT: GrowwAPI.ORDER_TYPE_LIMIT,
}

EXCHANGE_MAP = {
    Exchange.NSE: GrowwAPI.EXCHANGE_NSE,
    Exchange.BSE: GrowwAPI.EXCHANGE_BSE,
}


def segment_for(exchange: Exchange) -> str:
    """Currently constant (SEGMENT_CASH). Kept as a function so if F&O
    support is ever added, the switch happens here without touching
    the adapter."""
    del exchange
    return GrowwAPI.SEGMENT_CASH

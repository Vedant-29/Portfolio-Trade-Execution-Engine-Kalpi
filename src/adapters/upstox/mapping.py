"""Canonical ↔ Upstox field translation.

Key divergences from our canonical vocabulary:
  - Product: Upstox uses `D` (Delivery) / `I` (Intraday), not `CNC` /
    `MIS`. Simple one-to-one map.
  - Exchange: Upstox embeds the segment — `NSE_EQ`, `BSE_EQ`. Same shape.
"""

from __future__ import annotations

from src.schemas import Action, Exchange, PriceType, ProductType


def action_to_upstox(action: Action) -> str:
    return action.value

_PRODUCT_MAP = {
    ProductType.CNC: "D",
    ProductType.MIS: "I",
}

def product_to_upstox(product: ProductType) -> str:
    return _PRODUCT_MAP[product]

def price_type_to_upstox(price_type: PriceType) -> str:
    return price_type.value

_EXCHANGE_SEGMENT = {
    Exchange.NSE: "NSE_EQ",
    Exchange.BSE: "BSE_EQ",
}

def exchange_segment(exchange: Exchange) -> str:
    return _EXCHANGE_SEGMENT[exchange]

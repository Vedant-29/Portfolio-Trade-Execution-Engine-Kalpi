"""Canonical ↔ Zerodha field translation.

Zerodha's wire vocabulary happens to align with ours (BUY/SELL,
MARKET/LIMIT, CNC/MIS, NSE/BSE verbatim), so these are one-line
passthroughs. Isolated here so if Kite ever renames anything we touch
one file, not the adapter.
"""

from __future__ import annotations

from src.schemas import Action, Exchange, PriceType, ProductType


def action_to_kite(action: Action) -> str:
    return action.value

def product_to_kite(product: ProductType) -> str:
    return product.value

def price_type_to_kite(price_type: PriceType) -> str:
    return price_type.value

def exchange_to_kite(exchange: Exchange) -> str:
    return exchange.value

def exchange_from_kite(wire: str) -> Exchange:
    return Exchange(wire)

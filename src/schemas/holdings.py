from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from src.schemas.orders import Exchange


class Holding(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: Exchange
    quantity: int = Field(ge=0)
    average_price: Decimal | None = None

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Action(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

class ProductType(StrEnum):
    """Type of transaction basically -- supporting only 2 for now, F&O is not included in the current scope"""

    CNC = "CNC"
    MIS = "MIS"

class PriceType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"

class OrderStatus(StrEnum):
    PLACED = "PLACED"
    FAILED = "FAILED"

class OrderRequest(BaseModel):
    """Canonical order request — what the service layer speaks.

    Every adapter translates this into its broker's wire format.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, description="Trading symbol, e.g. 'RELIANCE'")
    exchange: Exchange
    action: Action
    quantity: int = Field(gt=0)
    price_type: PriceType = PriceType.MARKET
    product: ProductType = ProductType.CNC
    price: Decimal | None = None
    amo: bool = Field(
        default=False,
        description=(
            "After-Market Order. Queues on the broker until the next "
            "9:15 AM IST open. Zerodha requires LIMIT when amo=True."
        ),
    )

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _limit_orders_need_price(self) -> OrderRequest:
        if self.price_type is PriceType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require `price`")
        if self.price_type is PriceType.MARKET and self.price is not None:

            pass
        return self

class OrderResult(BaseModel):
    """What the adapter returns for a single order attempt."""

    request: OrderRequest
    status: Literal[OrderStatus.PLACED, OrderStatus.FAILED]
    broker_order_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def placed(cls, request: OrderRequest, broker_order_id: str) -> OrderResult:
        return cls(
            request=request,
            status=OrderStatus.PLACED,
            broker_order_id=broker_order_id,
        )

    @classmethod
    def failed(
        cls,
        request: OrderRequest,
        *,
        code: str,
        message: str,
    ) -> OrderResult:
        return cls(
            request=request,
            status=OrderStatus.FAILED,
            error_code=code,
            error_message=message,
        )

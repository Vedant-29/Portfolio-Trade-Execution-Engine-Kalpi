from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.orders import Exchange, OrderResult, PriceType, ProductType


class _SymbolItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    exchange: Exchange
    product: ProductType = ProductType.CNC
    price_type: PriceType = PriceType.MARKET
    price: Decimal | None = None
    amo: bool = False

    @model_validator(mode="after")
    def _limit_orders_need_price(self) -> _SymbolItem:
        if self.price_type is PriceType.LIMIT and self.price is None:
            raise ValueError("LIMIT items require `price`")
        return self

class FirstTimeItem(_SymbolItem):
    """A stock to BUY in a fresh portfolio."""

    quantity: int = Field(gt=0)

class SellItem(_SymbolItem):
    """A stock to SELL (exit) during a rebalance."""

    quantity: int = Field(gt=0)

class BuyItem(_SymbolItem):
    """A new stock to BUY during a rebalance."""

    quantity: int = Field(gt=0)

class AdjustItem(_SymbolItem):
    """Adjustment for an existing holding. delta > 0 → BUY; delta < 0 → SELL."""

    delta: int = Field(description="Positive = buy more; negative = sell off")

    @model_validator(mode="after")
    def _delta_nonzero(self) -> AdjustItem:
        if self.delta == 0:
            raise ValueError("AdjustItem.delta must be non-zero")
        return self

class RebalancePayload(BaseModel):
    sell: list[SellItem] = Field(default_factory=list)
    buy_new: list[BuyItem] = Field(default_factory=list)
    adjust: list[AdjustItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one(self) -> RebalancePayload:
        if not (self.sell or self.buy_new or self.adjust):
            raise ValueError("Rebalance payload must contain at least one instruction")
        return self

class PortfolioExecuteRequest(BaseModel):
    broker: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mode: Literal["first_time", "rebalance"]
    first_time: list[FirstTimeItem] | None = None
    rebalance: RebalancePayload | None = None

    @model_validator(mode="after")
    def _mode_matches_payload(self) -> PortfolioExecuteRequest:
        if self.mode == "first_time":
            if not self.first_time:
                raise ValueError("mode='first_time' requires `first_time` list")
            if self.rebalance is not None:
                raise ValueError("mode='first_time' must not include `rebalance`")
        else:
            if self.rebalance is None:
                raise ValueError("mode='rebalance' requires `rebalance` payload")
            if self.first_time is not None:
                raise ValueError("mode='rebalance' must not include `first_time`")
        return self

class ExecutionSummary(BaseModel):
    broker: str
    mode: Literal["first_time", "rebalance"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    successes: list[OrderResult] = Field(default_factory=list)
    failures: list[OrderResult] = Field(default_factory=list)

    @property
    def total_orders(self) -> int:
        return len(self.successes) + len(self.failures)

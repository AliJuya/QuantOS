from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from qcore.domain.enums import ExecutionStatus, OrderSide
from qcore.domain.ids import FillId, OrderId, StrategyId
from qcore.domain.types import ExitPolicy, Money, Price, Quantity, Symbol, Venue, ensure_utc


@dataclass(frozen=True, slots=True)
class OrderAccepted:
    order_id: OrderId
    symbol: Symbol
    side: OrderSide
    quantity: Quantity
    venue: Venue
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class OrderRejected:
    order_id: OrderId
    symbol: Symbol
    reason: str
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class OrderCanceled:
    order_id: OrderId
    symbol: Symbol
    reason: str
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class FillEvent:
    fill_id: FillId
    order_id: OrderId
    symbol: Symbol
    side: OrderSide
    quantity: Quantity
    fill_price: Price
    venue: Venue
    timestamp: datetime
    fee: Money
    slippage_bps: Decimal
    strategy_id: StrategyId | None = None
    exit_policy: ExitPolicy | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))
        object.__setattr__(self, "slippage_bps", Decimal(str(self.slippage_bps)))

    @property
    def signed_quantity(self) -> Decimal:
        if self.side is OrderSide.BUY:
            return self.quantity.value
        return -self.quantity.value

    @property
    def status(self) -> ExecutionStatus:
        return ExecutionStatus.FILLED

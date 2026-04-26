from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from qcore.domain.enums import OrderSide, OrderType, TimeInForce
from qcore.domain.ids import InstructionId, OrderId, StrategyId
from qcore.domain.types import ExitPolicy, Price, Quantity, Symbol, ensure_utc


@dataclass(frozen=True, slots=True)
class OrderRequest:
    order_id: OrderId
    instruction_id: InstructionId
    symbol: Symbol
    side: OrderSide
    quantity: Quantity
    order_type: OrderType
    time_in_force: TimeInForce
    timestamp: datetime
    limit_price: Price | None = None
    strategy_id: StrategyId | None = None
    exit_policy: ExitPolicy | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

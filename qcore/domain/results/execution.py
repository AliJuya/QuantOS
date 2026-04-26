from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from qcore.domain.enums import ExecutionStatus, OrderSide
from qcore.domain.events import FillEvent
from qcore.domain.ids import DecisionId, InstructionId, OrderId, StrategyId
from qcore.domain.types import ExitPolicy, Quantity, Symbol, ensure_utc


@dataclass(frozen=True, slots=True)
class ExecutionInstruction:
    instruction_id: InstructionId
    decision_id: DecisionId
    symbol: Symbol
    side: OrderSide
    quantity: Quantity
    target_quantity: Quantity
    current_quantity: Quantity
    timestamp: datetime
    strategy_id: StrategyId | None = None
    exit_policy: ExitPolicy | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    order_id: OrderId
    symbol: Symbol
    status: ExecutionStatus
    timestamp: datetime
    message: str
    fill: FillEvent | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

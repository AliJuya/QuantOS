from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcore.accounting.portfolio_state.engine import AccountingEngine
from qcore.domain.enums import OrderSide
from qcore.domain.ids import InstructionId
from qcore.domain.results import ExecutionInstruction, RiskDecision
from qcore.domain.types import Quantity, to_decimal


@dataclass(slots=True)
class BasicExecutionPlanner:
    accounting: AccountingEngine
    min_trade_quantity: Decimal

    def __post_init__(self) -> None:
        self.min_trade_quantity = to_decimal(self.min_trade_quantity)

    def on_risk_decision(self, decision: RiskDecision) -> ExecutionInstruction | None:
        if not decision.approved or decision.approved_target is None:
            return None

        target = decision.approved_target
        symbol = target.symbol
        strategy_id = target.strategy_id
        current_quantity = self.accounting.position_quantity(symbol, strategy_id=strategy_id)
        aggregate_current_quantity = self.accounting.position_quantity(symbol)
        target_quantity = target.target_quantity.value
        aggregate_target_quantity = aggregate_current_quantity - current_quantity + target_quantity
        delta = target_quantity - current_quantity
        if abs(delta) < self.min_trade_quantity:
            return None

        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        metadata = dict(decision.metadata)
        metadata.update({
            "delta_quantity": str(delta),
            "target_quantity": str(target_quantity),
            "current_quantity": str(current_quantity),
            "aggregate_current_quantity": str(aggregate_current_quantity),
            "aggregate_target_quantity": str(aggregate_target_quantity),
        })
        return ExecutionInstruction(
            instruction_id=InstructionId(f"{decision.decision_id}:instruction"),
            decision_id=decision.decision_id,
            symbol=symbol,
            side=side,
            quantity=Quantity(abs(delta)),
            target_quantity=target.target_quantity,
            current_quantity=Quantity(current_quantity),
            timestamp=decision.timestamp,
            strategy_id=strategy_id,
            exit_policy=target.exit_policy,
            metadata=metadata,
        )

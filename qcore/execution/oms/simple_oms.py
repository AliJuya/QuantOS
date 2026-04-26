from __future__ import annotations

from dataclasses import dataclass, field

from qcore.domain.commands import OrderRequest
from qcore.domain.enums import OrderType, TimeInForce
from qcore.domain.results import ExecutionInstruction
from qcore.domain.ids import OrderId


@dataclass(slots=True)
class SimpleOMS:
    order_sequence: int = 0

    def on_execution_instruction(self, instruction: ExecutionInstruction) -> OrderRequest:
        self.order_sequence += 1
        return OrderRequest(
            order_id=OrderId(f"order-{self.order_sequence:08d}"),
            instruction_id=instruction.instruction_id,
            symbol=instruction.symbol,
            side=instruction.side,
            quantity=instruction.quantity,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IOC,
            timestamp=instruction.timestamp,
            strategy_id=instruction.strategy_id,
            exit_policy=instruction.exit_policy,
            metadata=instruction.metadata,
        )

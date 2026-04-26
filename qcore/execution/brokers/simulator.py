from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcore.data.stores import MarketStore
from qcore.domain.commands import OrderRequest
from qcore.domain.enums import ExecutionStatus, OrderSide
from qcore.domain.events import FillEvent, OrderAccepted, OrderRejected
from qcore.domain.ids import FillId
from qcore.domain.results import ExecutionReport
from qcore.domain.types import Money, Price, Venue, to_decimal


@dataclass(slots=True)
class SimulatedBroker:
    market_store: MarketStore
    venue: Venue
    fee_bps: Decimal
    slippage_bps: Decimal
    fill_sequence: int = 0

    def __post_init__(self) -> None:
        self.fee_bps = to_decimal(self.fee_bps)
        self.slippage_bps = to_decimal(self.slippage_bps)

    def on_order_request(self, order: OrderRequest) -> list[object]:
        forced_fill_price = order.metadata.get("forced_fill_price") if order.metadata else None
        market_price = self.market_store.price_for(order.symbol)
        if market_price is None and forced_fill_price is None:
            rejected = OrderRejected(
                order_id=order.order_id,
                symbol=order.symbol,
                reason="missing market price",
                timestamp=order.timestamp,
            )
            return [
                rejected,
                ExecutionReport(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    status=ExecutionStatus.REJECTED,
                    timestamp=order.timestamp,
                    message=rejected.reason,
                ),
            ]

        base_price = to_decimal(forced_fill_price) if forced_fill_price is not None else market_price.value
        self.fill_sequence += 1
        direction = Decimal("1") if order.side is OrderSide.BUY else Decimal("-1")
        fill_price_value = base_price * (Decimal("1") + (direction * self.slippage_bps / Decimal("10000")))
        notional = fill_price_value * order.quantity.value
        fee = Money(notional * self.fee_bps / Decimal("10000"))
        fill = FillEvent(
            fill_id=FillId(f"fill-{self.fill_sequence:08d}"),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=Price(fill_price_value),
            venue=self.venue,
            timestamp=order.timestamp,
            fee=fee,
            slippage_bps=self.slippage_bps,
            strategy_id=order.strategy_id,
            exit_policy=order.exit_policy,
            metadata=order.metadata,
        )
        accepted = OrderAccepted(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            venue=self.venue,
            timestamp=order.timestamp,
        )
        report = ExecutionReport(
            order_id=order.order_id,
            symbol=order.symbol,
            status=ExecutionStatus.FILLED,
            timestamp=order.timestamp,
            message="filled by simulator",
            fill=fill,
        )
        return [accepted, fill, report]

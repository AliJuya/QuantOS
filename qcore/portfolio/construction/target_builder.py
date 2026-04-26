from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from qcore.accounting.portfolio_state.engine import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.enums import SignalSide
from qcore.domain.ids import TargetId
from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal, PortfolioTarget, Price, Quantity, to_decimal


@dataclass(slots=True)
class TargetBuilder:
    accounting: AccountingEngine
    market_store: MarketStore
    target_notional_fraction: Decimal
    quantity_step: Decimal

    def __post_init__(self) -> None:
        self.target_notional_fraction = to_decimal(self.target_notional_fraction)
        self.quantity_step = to_decimal(self.quantity_step)

    def on_gate_decision(self, decision: GateDecision) -> PortfolioTarget | None:
        signal = decision.approved_signal
        if signal is None:
            return None
        price = self.market_store.price_for(signal.symbol)
        if price is None:
            return None

        raw_quantity_override = signal.metadata.get("position_size")
        if raw_quantity_override is not None:
            raw_quantity = to_decimal(raw_quantity_override)
        else:
            equity = self.accounting.equity_amount()
            if equity <= 0:
                equity = self.accounting.cash_amount

            target_notional = equity * self.target_notional_fraction
            raw_quantity = target_notional / price.value
        stepped_quantity = raw_quantity.quantize(self.quantity_step, rounding=ROUND_DOWN)
        if signal.side is SignalSide.SHORT:
            stepped_quantity *= Decimal("-1")
        if signal.side is SignalSide.FLAT:
            stepped_quantity = Decimal("0")

        return PortfolioTarget(
            target_id=TargetId(f"{signal.alpha_id}:target"),
            alpha_id=signal.alpha_id,
            symbol=signal.symbol,
            target_quantity=Quantity(stepped_quantity),
            target_price=Price(price.value),
            timestamp=signal.timestamp,
            strategy_id=signal.strategy_id,
            exit_policy=signal.exit_policy,
            metadata={
                "strategy_id": str(signal.strategy_id),
                "signal_side": signal.side.value,
                "confidence": signal.confidence,
                "fraction": str(self.target_notional_fraction),
                "position_size_override": None if raw_quantity_override is None else str(raw_quantity_override),
                "signal_metadata": dict(signal.metadata),
            },
        )

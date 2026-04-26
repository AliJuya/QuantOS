from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.enums import RiskStatus
from qcore.domain.ids import DecisionId
from qcore.domain.results import RiskDecision
from qcore.domain.types import PortfolioTarget, Symbol, to_decimal


@dataclass(slots=True)
class BasicRiskManager:
    accounting: AccountingEngine
    market_store: MarketStore
    max_abs_position_quantity: Decimal
    max_abs_notional: Decimal
    allow_short: bool = True

    def __post_init__(self) -> None:
        self.max_abs_position_quantity = to_decimal(self.max_abs_position_quantity)
        self.max_abs_notional = to_decimal(self.max_abs_notional)

    def on_portfolio_target(self, target: PortfolioTarget) -> RiskDecision:
        price = self.market_store.price_for(target.symbol)
        if price is None:
            return self._decision(target, RiskStatus.REJECTED, "missing market price")
        current_strategy_quantity = self.accounting.position_quantity(target.symbol, strategy_id=target.strategy_id)
        current_aggregate_quantity = self.accounting.position_quantity(target.symbol)
        proposed_quantity = current_aggregate_quantity - current_strategy_quantity + target.target_quantity.value
        common_metadata = {
            "current_strategy_quantity": str(current_strategy_quantity),
            "current_aggregate_quantity": str(current_aggregate_quantity),
            "proposed_aggregate_quantity": str(proposed_quantity),
            "price": str(price.value),
            "proposed_aggregate_notional": str(abs(proposed_quantity) * price.value),
        }

        if not self.allow_short and target.target_quantity.value < 0:
            return self._decision(target, RiskStatus.REJECTED, "shorting disabled", metadata=common_metadata)
        if not self.allow_short and proposed_quantity < 0:
            return self._decision(target, RiskStatus.REJECTED, "aggregate shorting disabled", metadata=common_metadata)
        if abs(proposed_quantity) > self.max_abs_position_quantity:
            return self._decision(target, RiskStatus.REJECTED, "position limit exceeded", metadata=common_metadata)

        notional = abs(proposed_quantity) * price.value
        if notional > self.max_abs_notional:
            return self._decision(target, RiskStatus.REJECTED, "notional limit exceeded", metadata=common_metadata)
        return self._decision(
            target,
            RiskStatus.APPROVED,
            "approved",
            metadata=common_metadata,
        )

    def _decision(
        self,
        target: PortfolioTarget,
        status: RiskStatus,
        reason: str,
        metadata: dict[str, str] | None = None,
    ) -> RiskDecision:
        decision_metadata = dict(target.metadata)
        if metadata:
            decision_metadata.update(metadata)
        return RiskDecision(
            decision_id=DecisionId(f"{target.target_id}:{status}"),
            target_id=target.target_id,
            status=status,
            approved_target=target if status is RiskStatus.APPROVED else None,
            reason=reason,
            timestamp=target.timestamp,
            metadata=decision_metadata,
        )

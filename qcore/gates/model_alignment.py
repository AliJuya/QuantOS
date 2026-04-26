from __future__ import annotations

from dataclasses import dataclass

from qcore.domain.enums import SignalSide
from qcore.domain.ids import GateId, ModelId
from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal, Timeframe
from qcore.models.view import ModelView


@dataclass(slots=True)
class ModelAlignmentGate:
    gate_id: GateId
    timeframe: Timeframe
    regime_model_id: ModelId | None = None
    volatility_model_id: ModelId | None = None
    require_regime_alignment: bool = True
    max_annualized_vol: float | None = None
    allow_unready: bool = True

    def decide(self, signal: AlphaSignal, model_view: ModelView) -> GateDecision:
        if self.regime_model_id is not None:
            regime = model_view.latest_regime(
                model_id=self.regime_model_id,
                symbol=signal.symbol,
                timeframe=self.timeframe,
            )
            if regime is None or not regime.ready:
                if not self.allow_unready:
                    return GateDecision(
                        gate_id=self.gate_id,
                        alpha_id=signal.alpha_id,
                        approved_signal=None,
                        reason="regime_unready",
                        timestamp=signal.timestamp,
                    )
            elif self.require_regime_alignment and not self._regime_allows(signal.side, regime.regime):
                return GateDecision(
                    gate_id=self.gate_id,
                    alpha_id=signal.alpha_id,
                    approved_signal=None,
                    reason=f"regime_mismatch:{regime.regime}",
                    timestamp=signal.timestamp,
                    metadata={"regime": regime.regime, "score": regime.score},
                )

        if self.volatility_model_id is not None and self.max_annualized_vol is not None:
            vol = model_view.latest_volatility(
                model_id=self.volatility_model_id,
                symbol=signal.symbol,
                timeframe=self.timeframe,
            )
            if vol is None or not vol.ready:
                if not self.allow_unready:
                    return GateDecision(
                        gate_id=self.gate_id,
                        alpha_id=signal.alpha_id,
                        approved_signal=None,
                        reason="volatility_unready",
                        timestamp=signal.timestamp,
                    )
            elif vol.annualized_vol > self.max_annualized_vol:
                return GateDecision(
                    gate_id=self.gate_id,
                    alpha_id=signal.alpha_id,
                    approved_signal=None,
                    reason="volatility_too_high",
                    timestamp=signal.timestamp,
                    metadata={
                        "annualized_vol": vol.annualized_vol,
                        "max_annualized_vol": self.max_annualized_vol,
                    },
                )

        return GateDecision(
            gate_id=self.gate_id,
            alpha_id=signal.alpha_id,
            approved_signal=signal,
            reason="approved",
            timestamp=signal.timestamp,
        )

    @staticmethod
    def _regime_allows(side: SignalSide, regime: str) -> bool:
        if side is SignalSide.LONG:
            return regime == "bull"
        if side is SignalSide.SHORT:
            return regime == "bear"
        return True

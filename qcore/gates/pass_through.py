from __future__ import annotations

from dataclasses import dataclass

from qcore.domain.ids import GateId
from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal


@dataclass(frozen=True, slots=True)
class PassThroughGate:
    gate_id: GateId

    def decide(self, signal: AlphaSignal, model_view: object) -> GateDecision:
        del model_view
        return GateDecision(
            gate_id=self.gate_id,
            alpha_id=signal.alpha_id,
            approved_signal=signal,
            reason="approved",
            timestamp=signal.timestamp,
            metadata={},
        )

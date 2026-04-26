from __future__ import annotations

from dataclasses import dataclass

from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal
from qcore.models.view import ModelView


@dataclass(slots=True)
class GateEngine:
    gates: tuple[object, ...]
    model_view: ModelView

    def on_alpha_signal(self, signal: AlphaSignal) -> GateDecision:
        last_decision: GateDecision | None = None
        for gate in self.gates:
            decision = gate.decide(signal, self.model_view)
            last_decision = decision
            if not decision.approved:
                return decision
            if decision.approved_signal is not None:
                signal = decision.approved_signal
        if last_decision is not None:
            return last_decision
        raise ValueError("GateEngine requires at least one gate")

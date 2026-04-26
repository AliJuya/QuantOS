from __future__ import annotations

from typing import Any

from qcore.domain.ids import GateId, ModelId
from qcore.domain.types import Timeframe
from qcore.gates import GateEngine, ModelAlignmentGate, PassThroughGate
from qcore.models import ModelEngine
from qcore.registry.base import ComponentRegistry

_registry: ComponentRegistry[object] = ComponentRegistry("gate")


def _build_pass_through(cfg: dict[str, Any]) -> PassThroughGate:
    return PassThroughGate(
        gate_id=GateId(str(cfg.get("gate_id", "gate.pass_through"))),
    )


def _build_model_alignment(cfg: dict[str, Any]) -> ModelAlignmentGate:
    return ModelAlignmentGate(
        gate_id=GateId(str(cfg.get("gate_id", "gate.model_alignment"))),
        timeframe=Timeframe(str(cfg["timeframe"])),
        regime_model_id=ModelId(str(cfg["regime_model_id"])) if cfg.get("regime_model_id") else None,
        volatility_model_id=ModelId(str(cfg["volatility_model_id"])) if cfg.get("volatility_model_id") else None,
        require_regime_alignment=bool(cfg.get("require_regime_alignment", False)),
        max_annualized_vol=float(cfg["max_annualized_vol"]) if cfg.get("max_annualized_vol") is not None else None,
        allow_unready=bool(cfg.get("allow_unready", True)),
    )


_registry.register("pass_through", _build_pass_through)
_registry.register("model_alignment", _build_model_alignment)


def build_gate_engine(cfgs: list[dict[str, Any]], model_engine: ModelEngine) -> GateEngine:
    if not cfgs:
        cfgs = [{"kind": "pass_through", "gate_id": "gate.pass_through"}]
    gates = tuple(_registry.build(cfg) for cfg in cfgs)
    return GateEngine(gates=gates, model_view=model_engine.view)

from __future__ import annotations

from typing import Any

from qcore.domain.ids import ModelId
from qcore.domain.types import Timeframe
from qcore.models.regime import EmaTrendRegimeModel
from qcore.models.vol import EwmaVolatilityModel
from qcore.registry.base import ComponentRegistry

_registry: ComponentRegistry[object] = ComponentRegistry("model")


def _build_ewma_vol(cfg: dict[str, Any]) -> EwmaVolatilityModel:
    return EwmaVolatilityModel(
        model_id=ModelId(str(cfg.get("model_id", "volatility.ewma"))),
        timeframe=Timeframe(str(cfg["timeframe"])),
        lookback=int(cfg.get("lookback", 20)),
        annualization_factor=int(cfg.get("annualization_factor", 365)),
    )


def _build_ema_regime(cfg: dict[str, Any]) -> EmaTrendRegimeModel:
    return EmaTrendRegimeModel(
        model_id=ModelId(str(cfg.get("model_id", "regime.ema"))),
        timeframe=Timeframe(str(cfg["timeframe"])),
        fast_period=int(cfg.get("fast_period", 5)),
        slow_period=int(cfg.get("slow_period", 20)),
    )


_registry.register("ewma_vol", _build_ewma_vol)
_registry.register("ema_regime", _build_ema_regime)


def build_model(cfg: dict[str, Any]) -> object:
    return _registry.build(cfg)


def build_models(cfgs: list[dict[str, Any]]) -> tuple[object, ...]:
    return tuple(build_model(cfg) for cfg in cfgs)

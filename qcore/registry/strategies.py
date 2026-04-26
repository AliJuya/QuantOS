from __future__ import annotations

from typing import Any

from qcore.alpha.strategies import (
    EmaCrossStrategy,
)
from qcore.domain.ids import StrategyId
from qcore.domain.types import Timeframe
from qcore.registry.base import ComponentRegistry

_registry: ComponentRegistry[object] = ComponentRegistry("strategy")


def _build_ema_cross(cfg: dict[str, Any], source_timeframe: Timeframe) -> EmaCrossStrategy:
    configured_tf = cfg.get("input_timeframe")
    return EmaCrossStrategy(
        strategy_id=StrategyId(str(cfg["strategy_id"])),
        short_period=int(cfg["short_period"]),
        long_period=int(cfg["long_period"]),
        signal_horizon=Timeframe(str(cfg["signal_horizon"])),
        input_timeframe=Timeframe(str(configured_tf)) if configured_tf else source_timeframe,
        stop_loss_fraction=float(cfg["stop_loss_fraction"]) if cfg.get("stop_loss_fraction") is not None else None,
        take_profit_fraction=float(cfg["take_profit_fraction"]) if cfg.get("take_profit_fraction") is not None else None,
        trailing_stop_fraction=float(cfg["trailing_stop_fraction"]) if cfg.get("trailing_stop_fraction") is not None else None,
        trailing_stop_amount=float(cfg["trailing_stop_amount"]) if cfg.get("trailing_stop_amount") is not None else None,
        max_hold_bars=int(cfg["max_hold_bars"]) if cfg.get("max_hold_bars") is not None else None,
        exit_on_session_close=bool(cfg.get("exit_on_session_close", False)),
    )


_registry.register("ema_cross", _build_ema_cross)


def build_strategy(cfg: dict[str, Any], source_timeframe: Timeframe) -> object:
    return _registry.build(cfg, source_timeframe=source_timeframe)


def build_strategies(cfgs: list[dict[str, Any]], source_timeframe: Timeframe) -> tuple[object, ...]:
    if not cfgs:
        raise ValueError("strategy config requires at least one strategy")
    return tuple(build_strategy(cfg, source_timeframe) for cfg in cfgs)

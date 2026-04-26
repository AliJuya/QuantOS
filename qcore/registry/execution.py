from __future__ import annotations

from typing import Any

from qcore.domain.types import Venue
from qcore.execution.brokers import SimulatedBroker
from qcore.execution.planner import BasicExecutionPlanner
from qcore.registry.base import ComponentRegistry

_planner_registry: ComponentRegistry[object] = ComponentRegistry("execution_planner")
_broker_registry: ComponentRegistry[object] = ComponentRegistry("execution_broker")


def _build_basic_planner(cfg: dict[str, Any], accounting: object) -> BasicExecutionPlanner:
    return BasicExecutionPlanner(
        accounting=accounting,
        min_trade_quantity=cfg["min_trade_quantity"],
    )


def _build_simulated_broker(cfg: dict[str, Any], market_store: object) -> SimulatedBroker:
    return SimulatedBroker(
        market_store=market_store,
        venue=Venue(str(cfg["venue"])),
        fee_bps=cfg["fee_bps"],
        slippage_bps=cfg["slippage_bps"],
    )


_planner_registry.register("basic", _build_basic_planner)
_broker_registry.register("simulated", _build_simulated_broker)


def build_planner(exec_cfg: dict[str, Any], accounting: object) -> object:
    kind = str(exec_cfg.get("planner", "basic"))
    return _planner_registry.build({**exec_cfg, "kind": kind}, accounting=accounting)


def build_broker(exec_cfg: dict[str, Any], market_store: object) -> object:
    kind = str(exec_cfg.get("broker", "simulated"))
    return _broker_registry.build({**exec_cfg, "kind": kind}, market_store=market_store)

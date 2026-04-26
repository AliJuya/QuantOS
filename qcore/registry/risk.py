from __future__ import annotations

from typing import Any

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.registry.base import ComponentRegistry
from qcore.risk.pre_trade import BasicRiskManager

_registry: ComponentRegistry[object] = ComponentRegistry("risk")


def _build_basic(cfg: dict[str, Any], market_store: object, accounting: AccountingEngine) -> BasicRiskManager:
    return BasicRiskManager(
        accounting=accounting,
        market_store=market_store,
        max_abs_position_quantity=cfg["max_abs_position_quantity"],
        max_abs_notional=cfg["max_abs_notional"],
        allow_short=bool(cfg.get("allow_short", True)),
    )


_registry.register("basic", _build_basic)


def build_risk(cfg: dict[str, Any], market_store: object, accounting: AccountingEngine) -> object:
    return _registry.build(cfg, market_store=market_store, accounting=accounting)

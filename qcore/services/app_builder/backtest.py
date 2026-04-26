from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.analytics.recorder import RunRecorder
from qcore.data import MarketDataEngine
from qcore.data.replay import ReplayIngestionRuntime, ReplaySourceFactory
from qcore.domain.contracts import MarketDataSourceProtocol
from qcore.domain.ids import RunId
from qcore.domain.types import RunManifest, Timeframe
from qcore.execution.fills import BracketExitEngine
from qcore.execution.oms import SimpleOMS
from qcore.kernel.clock import ReplayClock
from qcore.kernel.event_bus import SynchronousEventBus
from qcore.models import ModelEngine
from qcore.portfolio.construction import TargetBuilder
from qcore.registry import (
    build_broker,
    build_calendar,
    build_gate_engine,
    build_models,
    build_planner,
    build_risk,
    build_strategies,
)


def config_digest(config: dict[str, Any]) -> str:
    import json

    encoded = json.dumps(config, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(slots=True)
class BacktestRuntime:
    source: MarketDataSourceProtocol
    clock: ReplayClock
    bus: SynchronousEventBus
    accounting: AccountingEngine
    recorder: RunRecorder
    manifest: RunManifest
    run_dir: Path


class BacktestAppBuilder:
    def __init__(
        self,
        config: dict[str, Any],
        config_path: Path,
        project_root: Path,
        run_id: str | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.project_root = project_root
        self.run_id = (
            run_id
            or config.get("run", {}).get("run_id")
            or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        )

    def build(self) -> BacktestRuntime:
        source_bundle = ReplaySourceFactory(self.project_root).build(self.config["data"])
        artifacts_root = self._resolve_path(self.config["run"]["artifacts_root"])
        run_dir = artifacts_root / self.run_id

        clock = ReplayClock()
        calendar = build_calendar(self.config.get("calendar") or {})
        models = build_models(self.config.get("models") or [])
        model_engine = ModelEngine(models=models)
        strategies = build_strategies(self.config["strategies"], source_bundle.source_timeframe)
        gate_engine = build_gate_engine(self.config["gates"], model_engine)

        aggregate_timeframes = tuple(
            Timeframe(str(v))
            for v in (self.config["data"].get("aggregate_timeframes") or ())
        )
        data_engine = MarketDataEngine.from_requirements(
            source_timeframe=source_bundle.source_timeframe,
            input_mode=source_bundle.input_mode,
            calendar=calendar,
            component_requirements=(*models, *strategies),
            aggregate_timeframes=aggregate_timeframes,
            river_maxlen=int(self.config["data"].get("river_maxlen", 50_000)),
        )
        market_view = data_engine.view
        for strategy in strategies:
            attach_market_view = getattr(strategy, "attach_market_view", None)
            if callable(attach_market_view):
                attach_market_view(market_view)
        market_store = data_engine.market_store
        accounting = AccountingEngine(
            market_store=market_store,
            starting_cash=self.config["portfolio"]["starting_cash"],
            base_currency=self.config["portfolio"].get("base_currency", "USD"),
        )
        portfolio = TargetBuilder(
            accounting=accounting,
            market_store=market_store,
            target_notional_fraction=self.config["portfolio"]["target_notional_fraction"],
            quantity_step=self.config["portfolio"]["quantity_step"],
        )
        risk = build_risk(self.config["risk"], market_store, accounting)
        planner = build_planner(self.config["execution"], accounting)
        oms = SimpleOMS()
        broker = build_broker(self.config["execution"], market_store)
        bracket_exit_engine = BracketExitEngine(
            source_timeframe=source_bundle.source_timeframe,
            calendar=calendar,
            intrabar_exit_policy=str(self.config["execution"].get("intrabar_exit_policy", "stop_first")),
        )

        from qcore.domain.commands import OrderRequest
        from qcore.domain.events import BarCloseEvent, FillEvent
        from qcore.domain.results import ExecutionInstruction, GateDecision, RiskDecision
        from qcore.domain.types import AlphaSignal, PortfolioTarget

        bus = SynchronousEventBus()
        bus.subscribe(BarCloseEvent, bracket_exit_engine.on_bar_close)
        ReplayIngestionRuntime(data_engine).register(bus)
        bus.subscribe(BarCloseEvent, model_engine.on_bar_close)
        for strategy in strategies:
            bus.subscribe(BarCloseEvent, strategy.on_bar_close)
        bus.subscribe(AlphaSignal, gate_engine.on_alpha_signal)
        bus.subscribe(GateDecision, portfolio.on_gate_decision)
        bus.subscribe(PortfolioTarget, risk.on_portfolio_target)
        bus.subscribe(RiskDecision, planner.on_risk_decision)
        bus.subscribe(ExecutionInstruction, oms.on_execution_instruction)
        bus.subscribe(OrderRequest, broker.on_order_request)
        bus.subscribe(FillEvent, bracket_exit_engine.on_fill)
        bus.subscribe(FillEvent, accounting.on_fill)
        for strategy in strategies:
            on_fill = getattr(strategy, "on_fill", None)
            if callable(on_fill):
                bus.subscribe(FillEvent, on_fill)

        manifest = RunManifest(
            run_id=RunId(self.run_id),
            app_name="backtester",
            mode="backtest",
            started_at=datetime.now(tz=UTC),
            completed_at=None,
            config_path=str(self.config_path.resolve()),
            data_path=self._manifest_data_path(source_bundle.source_locations),
            config_digest=config_digest(self.config),
            event_count=0,
            replay_checkpoint=None,
            metadata={
                "project_root": str(self.project_root.resolve()),
                "resolved_data_files": [str(p) for p in source_bundle.resolved_data_files],
                "source_descriptor": source_bundle.source.descriptor(),
                "calendar_config": deepcopy(self.config.get("calendar") or {}),
                "reporting_config": deepcopy(self.config.get("reporting") or {}),
                "data_engine": data_engine.stats(),
                "model_engine": model_engine.stats(),
                "execution": {
                    "intrabar_exit_policy": bracket_exit_engine.intrabar_exit_policy,
                    "source_timeframe": str(source_bundle.source_timeframe),
                    "managed_exit_engine": "managed",
                },
            },
        )
        recorder = RunRecorder(run_dir)
        return BacktestRuntime(
            source=source_bundle.source,
            clock=clock,
            bus=bus,
            accounting=accounting,
            recorder=recorder,
            manifest=manifest,
            run_dir=run_dir,
        )

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    @staticmethod
    def _manifest_data_path(source_locations: tuple[Path, ...]) -> str:
        if len(source_locations) == 1:
            return str(source_locations[0])
        return ";".join(str(p) for p in source_locations)

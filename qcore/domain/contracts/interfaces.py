from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from qcore.domain.commands import OrderRequest
from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.results import ExecutionInstruction, ExecutionReport, GateDecision, RiskDecision
from qcore.domain.types import (
    AlphaSignal,
    PortfolioSnapshot,
    PortfolioTarget,
    RegimeSnapshot,
    RunManifest,
    SourceDescriptor,
    Timeframe,
    VolatilitySnapshot,
)


EventHandler = Callable[[object], object | Iterable[object] | None]


class EventBusProtocol(Protocol):
    def subscribe(self, event_type: type[object], handler: EventHandler) -> None: ...

    def publish(self, event: object) -> tuple[object, ...]: ...


class ReplayClockProtocol(Protocol):
    def now(self) -> datetime | None: ...

    def advance_to(self, timestamp: datetime) -> datetime: ...


class MarketDataSourceProtocol(Protocol):
    def iter_events(self) -> Iterable[object]: ...

    def descriptor(self) -> SourceDescriptor: ...


class LiveMarketDataSourceProtocol(Protocol):
    def start(self, event_bus: EventBusProtocol) -> None: ...

    def stop(self) -> None: ...

    def descriptor(self) -> SourceDescriptor: ...


class AlphaStrategyProtocol(Protocol):
    def on_bar_close(self, event: BarCloseEvent) -> object | Iterable[object] | None: ...

    def required_timeframes(self) -> tuple[Timeframe, ...]: ...

    def warmup_requirements(self) -> Mapping[Timeframe, int]: ...


class StreamingModelProtocol(Protocol):
    def on_bar_close(self, event: BarCloseEvent) -> object | Iterable[object] | None: ...

    def required_timeframes(self) -> tuple[Timeframe, ...]: ...

    def warmup_requirements(self) -> Mapping[Timeframe, int]: ...


class GateEngineProtocol(Protocol):
    def on_alpha_signal(self, signal: AlphaSignal) -> GateDecision | None: ...


class PortfolioConstructionProtocol(Protocol):
    def on_gate_decision(self, decision: GateDecision) -> PortfolioTarget | None: ...


class RiskEngineProtocol(Protocol):
    def on_portfolio_target(self, target: PortfolioTarget) -> RiskDecision: ...


class ExecutionVenueProtocol(Protocol):
    def on_order_request(
        self,
        order: OrderRequest,
    ) -> object | Iterable[object] | None: ...


class AccountingEngineProtocol(Protocol):
    def on_fill(self, fill: FillEvent) -> object | Iterable[object] | None: ...

    def mark_to_market(self, timestamp: datetime) -> PortfolioSnapshot: ...


class RecorderProtocol(Protocol):
    def write_manifest(self, manifest: RunManifest) -> Path: ...

    def record_event(self, event: object) -> None: ...

    def record_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None: ...

    def write_summary(self, manifest: RunManifest, snapshot: PortfolioSnapshot) -> Path: ...

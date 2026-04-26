from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.ids import AlphaId, DecisionId, EntryId, GateId, InstructionId, ModelId, RunId, StrategyId, TargetId, TradeId
from qcore.domain.types.policies import ExitPolicy
from qcore.domain.types.primitives import Money, Price, Quantity, Symbol, Timeframe, Venue, ensure_utc


JsonMap = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AlphaSignal:
    alpha_id: AlphaId
    strategy_id: StrategyId
    symbol: Symbol
    side: SignalSide
    confidence: float
    horizon: Timeframe
    entry_style: EntryStyle
    thesis: str
    invalidation: str
    timestamp: datetime
    features_ref: str | None
    exit_policy: ExitPolicy | None = None
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class VolatilitySnapshot:
    model_id: ModelId
    symbol: Symbol
    timeframe: Timeframe
    timestamp: datetime
    annualized_vol: float
    return_std: float
    ready: bool
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class RegimeSnapshot:
    model_id: ModelId
    symbol: Symbol
    timeframe: Timeframe
    timestamp: datetime
    regime: str
    score: float
    ready: bool
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class PortfolioTarget:
    target_id: TargetId
    alpha_id: AlphaId
    symbol: Symbol
    target_quantity: Quantity
    target_price: Price
    timestamp: datetime
    strategy_id: StrategyId | None = None
    exit_policy: ExitPolicy | None = None
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: Symbol
    quantity: Quantity
    avg_price: Price | None
    mark_price: Price | None
    market_value: Money
    unrealized_pnl: Money
    realized_pnl: Money
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    cash: Money
    equity: Money
    fees_paid: Money
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    timestamp: datetime
    positions: tuple[PositionSnapshot, ...]
    balance: BalanceSnapshot
    realized_pnl: Money
    unrealized_pnl: Money
    net_pnl: Money

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    entry_id: EntryId
    timestamp: datetime
    symbol: Symbol | None
    entry_type: str
    amount: Money
    cash_after: Money
    realized_pnl_after: Money
    fee: Money
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    trade_id: TradeId
    strategy_id: StrategyId | None
    symbol: Symbol
    venue: Venue
    side: SignalSide
    quantity: Quantity
    entry_price: Price
    exit_price: Price
    entry_timestamp: datetime
    exit_timestamp: datetime
    realized_pnl: Money
    fees_paid: Money
    hold_seconds: int
    exit_reason: str | None
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_timestamp", ensure_utc(self.entry_timestamp))
        object.__setattr__(self, "exit_timestamp", ensure_utc(self.exit_timestamp))


@dataclass(frozen=True, slots=True)
class WarmupStatus:
    component_id: str
    symbol: Symbol
    ready: bool
    samples_seen: int
    samples_required: int
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    event_index: int
    timestamp: datetime
    last_event_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: str
    source_type: str
    mode: str
    ordering: str
    locations: tuple[Path, ...] = ()
    source_timeframe: str | None = None
    metadata: JsonMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: RunId
    app_name: str
    mode: str
    started_at: datetime
    completed_at: datetime | None
    config_path: str
    data_path: str
    config_digest: str
    event_count: int
    replay_checkpoint: ReplayCheckpoint | None
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", ensure_utc(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", ensure_utc(self.completed_at))

from __future__ import annotations

from dataclasses import dataclass, field

from qcore.data.aggregation import TimeframeBarAggregator
from qcore.data.calendars import AlwaysOpenCalendar, SessionContext, TradingCalendarProtocol
from qcore.data.ingestion import IncrementalEventBarBuilder
from qcore.data.stores import ClosedBarRiver
from qcore.data.stores import MarketStore
from qcore.data.view import MarketDataView
from qcore.data.warmup import WarmupRegistry, WarmupRequirement
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent
from qcore.domain.types import Symbol, Timeframe, Venue


def _normalize_timeframes(values: tuple[Timeframe, ...]) -> tuple[Timeframe, ...]:
    deduped = {value.value: value for value in values}
    return tuple(sorted(deduped.values(), key=lambda timeframe: timeframe.duration))


@dataclass(frozen=True, slots=True)
class MarketDataEngineConfig:
    source_timeframe: Timeframe
    input_mode: str = "bars"
    aggregate_timeframes: tuple[Timeframe, ...] = ()
    river_maxlen: int = 50_000
    calendar: TradingCalendarProtocol = field(default_factory=AlwaysOpenCalendar)

    def __post_init__(self) -> None:
        mode = str(self.input_mode).strip().lower()
        if mode not in {"bars", "ticks", "trades"}:
            raise ValueError("input_mode must be one of: bars, ticks, trades")
        object.__setattr__(self, "input_mode", mode)
        if self.river_maxlen <= 0:
            raise ValueError("river_maxlen must be positive")
        normalized = _normalize_timeframes(self.aggregate_timeframes)
        object.__setattr__(self, "aggregate_timeframes", normalized)

        for timeframe in self.aggregate_timeframes:
            if timeframe.duration <= self.source_timeframe.duration:
                raise ValueError("aggregate timeframe must be greater than source timeframe")
            if timeframe.duration.total_seconds() % self.source_timeframe.duration.total_seconds() != 0:
                raise ValueError("aggregate timeframe must be an integer multiple of source timeframe")

    def all_timeframes(self) -> tuple[Timeframe, ...]:
        return (self.source_timeframe,) + self.aggregate_timeframes


@dataclass(slots=True)
class MarketDataEngine:
    """
    Owns market-store writes plus upward aggregation from configured source streams.

    Current scope:
    - closed bar ingestion
    - append-only market store updates
    - upward aggregation from source timeframe -> configured higher timeframes

    This keeps data responsibilities in one layer rather than spreading them across
    the app builder, store, and strategy wiring.
    """

    config: MarketDataEngineConfig
    market_store: MarketStore = field(default_factory=MarketStore)
    aggregators: tuple[TimeframeBarAggregator, ...] = ()
    warmup_registry: WarmupRegistry = field(default_factory=WarmupRegistry)
    source_builder: IncrementalEventBarBuilder | None = None

    @classmethod
    def from_config(
        cls,
        config: MarketDataEngineConfig,
        *,
        warmup_requirements: tuple[WarmupRequirement, ...] = (),
    ) -> "MarketDataEngine":
        aggregators: list[TimeframeBarAggregator] = []
        if config.aggregate_timeframes:
            aggregators.append(
                TimeframeBarAggregator(
                    source_timeframe=config.source_timeframe,
                    output_timeframes=config.aggregate_timeframes,
                )
            )
        source_builder = None
        if config.input_mode in {"ticks", "trades"}:
            source_builder = IncrementalEventBarBuilder(
                source_timeframe=config.source_timeframe,
                input_mode=config.input_mode,
            )
        registry = WarmupRegistry()
        registry.extend(warmup_requirements)
        return cls(
            config=config,
            market_store=MarketStore(bar_river=ClosedBarRiver(maxlen=config.river_maxlen)),
            aggregators=tuple(aggregators),
            warmup_registry=registry,
            source_builder=source_builder,
        )

    @classmethod
    def from_requirements(
        cls,
        *,
        source_timeframe: Timeframe,
        input_mode: str = "bars",
        calendar: TradingCalendarProtocol | None = None,
        component_requirements: tuple[object, ...] = (),
        aggregate_timeframes: tuple[Timeframe, ...] = (),
        river_maxlen: int = 50_000,
    ) -> "MarketDataEngine":
        requested_timeframes = list(aggregate_timeframes)
        warmup_requirements: list[WarmupRequirement] = []

        for component in component_requirements:
            required_timeframes = getattr(component, "required_timeframes", None)
            if callable(required_timeframes):
                requested_timeframes.extend(required_timeframes())

            warmup_method = getattr(component, "warmup_requirements", None)
            if callable(warmup_method):
                bars_by_timeframe = warmup_method()
                warmup_requirements.append(
                    WarmupRequirement(
                        component_id=component.__class__.__name__,
                        bars_by_timeframe=bars_by_timeframe,
                    )
                )
                requested_timeframes.extend(bars_by_timeframe.keys())

        normalized_aggregates = tuple(
            timeframe
            for timeframe in _normalize_timeframes(tuple(requested_timeframes))
            if timeframe != source_timeframe
        )
        return cls.from_config(
            MarketDataEngineConfig(
                source_timeframe=source_timeframe,
                input_mode=input_mode,
                aggregate_timeframes=normalized_aggregates,
                river_maxlen=river_maxlen,
                calendar=calendar or AlwaysOpenCalendar(),
            ),
            warmup_requirements=tuple(warmup_requirements),
        )

    @classmethod
    def from_timeframes(
        cls,
        *,
        source_timeframe: Timeframe,
        input_mode: str = "bars",
        calendar: TradingCalendarProtocol | None = None,
        aggregate_timeframes: tuple[Timeframe, ...] = (),
        river_maxlen: int = 50_000,
    ) -> "MarketDataEngine":
        return cls.from_config(
            MarketDataEngineConfig(
                source_timeframe=source_timeframe,
                input_mode=input_mode,
                aggregate_timeframes=aggregate_timeframes,
                river_maxlen=river_maxlen,
                calendar=calendar or AlwaysOpenCalendar(),
            )
        )

    @property
    def view(self) -> MarketDataView:
        return MarketDataView(self.market_store, self.config.calendar)

    def on_bar_close(self, event: BarCloseEvent) -> list[BarCloseEvent]:
        self.market_store.on_bar_close(event)

        emitted: list[BarCloseEvent] = []
        for aggregator in self.aggregators:
            emitted.extend(aggregator.on_bar_close(event))
        return emitted

    def stats(self) -> dict[str, object]:
        return {
            "input_mode": self.config.input_mode,
            "source_timeframe": str(self.config.source_timeframe),
            "aggregate_timeframes": [str(timeframe) for timeframe in self.config.aggregate_timeframes],
            "market_store": self.market_store.stats(),
            "warmup": self.warmup_registry.stats(),
            "calendar": self.config.calendar.stats(),
        }

    def session_context(self, timestamp) -> SessionContext:
        return self.config.calendar.session_context(timestamp)

    def session_label_for(self, timestamp) -> str:
        return self.session_context(timestamp).session_label

    def on_tick(self, event: TickEvent) -> list[BarCloseEvent]:
        if self.source_builder is None:
            return []
        return self.source_builder.on_tick(event)

    def on_trade(self, event: TradeEvent) -> list[BarCloseEvent]:
        if self.source_builder is None:
            return []
        return self.source_builder.on_trade(event)

    def known_timeframes(self) -> tuple[Timeframe, ...]:
        return self.config.all_timeframes()

    def river(self, timeframe: Timeframe) -> tuple[BarCloseEvent, ...]:
        return tuple(
            bar
            for key in self.market_store.streams()
            if key.timeframe == timeframe
            for bar in self.market_store.window(symbol=key.symbol, venue=key.venue, timeframe=key.timeframe)
        )

    def seed_source_bars(self, events: tuple[BarCloseEvent, ...]) -> int:
        count = 0
        for event in sorted(events, key=lambda item: item.timestamp):
            if event.timeframe != self.config.source_timeframe:
                raise ValueError("seed_source_bars requires events at the configured source timeframe")
            self._ingest_bar_chain(event)
            count += 1
        return count

    def seed_timeframe_bars(
        self,
        *,
        timeframe: Timeframe,
        events: tuple[BarCloseEvent, ...],
        prepend: bool = False,
    ) -> int:
        if timeframe not in self.known_timeframes():
            raise ValueError(f"timeframe {timeframe} is not tracked by this data engine")
        for event in events:
            if event.timeframe != timeframe:
                raise ValueError("seed_timeframe_bars got event with mismatched timeframe")
        self.market_store.seed_bars(tuple(sorted(events, key=lambda item: item.timestamp)), prepend=prepend)
        return len(events)

    def _ingest_bar_chain(self, event: BarCloseEvent) -> None:
        queue = [event]
        while queue:
            current = queue.pop(0)
            self.market_store.on_bar_close(current)
            for aggregator in self.aggregators:
                queue.extend(aggregator.on_bar_close(current))

    def is_ready(
        self,
        *,
        symbol: Symbol,
        venue: Venue,
        timeframe: Timeframe,
    ) -> bool:
        required = self.warmup_registry.required_bars(timeframe)
        if required <= 0:
            return True
        return len(self.market_store.window(symbol=symbol, venue=venue, timeframe=timeframe, size=required)) >= required

    def readiness(
        self,
        *,
        symbol: Symbol,
        venue: Venue,
    ) -> dict[str, dict[str, int | bool]]:
        status: dict[str, dict[str, int | bool]] = {}
        for timeframe, required in self.warmup_registry.global_bars_by_timeframe().items():
            seen = len(self.market_store.window(symbol=symbol, venue=venue, timeframe=timeframe, size=required))
            status[str(timeframe)] = {
                "required": required,
                "seen": seen,
                "ready": seen >= required,
            }
        return status

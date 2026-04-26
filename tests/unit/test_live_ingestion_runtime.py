from dataclasses import dataclass, field
from datetime import UTC, datetime

from qcore.data import MarketDataEngine
from qcore.data.live import LiveIngestionRuntime
from qcore.domain.contracts import EventBusProtocol
from qcore.domain.events import BarCloseEvent, TradeEvent
from qcore.domain.types import Price, Quantity, SourceDescriptor, Symbol, Timeframe, Venue
from qcore.kernel.event_bus import SynchronousEventBus


@dataclass(slots=True)
class _FakeLiveTradeSource:
    emitted: tuple[TradeEvent, ...]
    started: bool = False
    stopped: bool = False
    published: list[tuple[object, ...]] = field(default_factory=list)

    def start(self, event_bus: EventBusProtocol) -> None:
        self.started = True
        for event in self.emitted:
            self.published.append(event_bus.publish(event))

    def stop(self) -> None:
        self.stopped = True

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_id="fake_live",
            source_type="test",
            mode="live",
            ordering="event_time",
        )


def test_live_ingestion_runtime_routes_live_trade_source_into_bars() -> None:
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    source = _FakeLiveTradeSource(
        emitted=(
            TradeEvent(symbol=symbol, venue=venue, price=Price("100"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)),
            TradeEvent(symbol=symbol, venue=venue, price=Price("101"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 0, 40, tzinfo=UTC)),
            TradeEvent(symbol=symbol, venue=venue, price=Price("102"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 1, 5, tzinfo=UTC)),
            TradeEvent(symbol=symbol, venue=venue, price=Price("103"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC)),
            TradeEvent(symbol=symbol, venue=venue, price=Price("104"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 2, 1, tzinfo=UTC)),
        )
    )
    engine = MarketDataEngine.from_timeframes(
        source_timeframe=Timeframe("1m"),
        input_mode="trades",
    )
    bus = SynchronousEventBus()
    observed_bars: list[BarCloseEvent] = []
    bus.subscribe(BarCloseEvent, observed_bars.append)

    runtime = LiveIngestionRuntime(data_engine=engine, source=source, event_bus=bus)
    runtime.start()
    runtime.stop()

    assert source.started is True
    assert source.stopped is True
    assert any(any(isinstance(event, BarCloseEvent) for event in published) for published in source.published)
    assert len(observed_bars) == 1
    assert observed_bars[0].timestamp == datetime(2026, 1, 1, 0, 2, 0, tzinfo=UTC)

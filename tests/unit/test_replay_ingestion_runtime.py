from datetime import UTC, datetime

from qcore.data import MarketDataEngine
from qcore.data.replay import ReplayIngestionRuntime
from qcore.domain.events import BarCloseEvent, TradeEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue
from qcore.kernel.event_bus import SynchronousEventBus


def test_replay_ingestion_runtime_routes_trade_source_into_bar_closes() -> None:
    engine = MarketDataEngine.from_timeframes(
        source_timeframe=Timeframe("1m"),
        input_mode="trades",
    )
    bus = SynchronousEventBus()
    ReplayIngestionRuntime(engine).register(bus)

    observed_bars: list[BarCloseEvent] = []
    bus.subscribe(BarCloseEvent, observed_bars.append)

    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    trade_times = (
        datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 0, 40, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 1, 5, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 2, 1, tzinfo=UTC),
    )
    prices = ("100", "101", "102", "103", "104")

    published = ()
    for timestamp, price in zip(trade_times, prices, strict=True):
        published = bus.publish(
            TradeEvent(
                symbol=symbol,
                venue=venue,
                price=Price(price),
                quantity=Quantity("1"),
                timestamp=timestamp,
            )
        )

    assert any(isinstance(event, BarCloseEvent) for event in published)
    assert len(observed_bars) == 1
    assert observed_bars[0].timestamp == datetime(2026, 1, 1, 0, 2, 0, tzinfo=UTC)
    assert engine.market_store.last_bar(symbol, venue=venue, timeframe=Timeframe("1m")) == observed_bars[0]

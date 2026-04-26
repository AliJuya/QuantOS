from datetime import UTC, datetime

from qcore.data import MarketDataEngine
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def test_market_data_engine_stores_base_and_emits_aggregated_bars() -> None:
    engine = MarketDataEngine.from_timeframes(
        source_timeframe=Timeframe("1m"),
        aggregate_timeframes=(Timeframe("5m"),),
    )
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")

    emitted = []
    for minute in range(10):
        close_timestamp = datetime(2026, 1, 1, 0, minute + 1, tzinfo=UTC)
        event = BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("1m"),
            bar_open_time=close_timestamp - Timeframe("1m").duration,
            open_price=Price(100 + minute),
            high_price=Price(101 + minute),
            low_price=Price(99 + minute),
            close_price=Price(100 + minute),
            volume=Quantity("1"),
            timestamp=close_timestamp,
        )
        emitted.extend(engine.on_bar_close(event))

    last_base = engine.market_store.last_bar(
        symbol,
        timeframe=Timeframe("1m"),
        venue=venue,
    )
    assert last_base is not None
    assert last_base.timestamp == datetime(2026, 1, 1, 0, 10, tzinfo=UTC)

    assert len(emitted) == 1
    aggregated = emitted[0]
    assert aggregated.timeframe == Timeframe("5m")
    assert aggregated.bar_open_time == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert aggregated.timestamp == datetime(2026, 1, 1, 0, 10, tzinfo=UTC)

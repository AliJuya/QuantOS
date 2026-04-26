from datetime import UTC, datetime

from qcore.data import MarketDataEngine
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def test_market_data_engine_seeds_source_bars_and_builds_higher_timeframe_history() -> None:
    engine = MarketDataEngine.from_timeframes(
        source_timeframe=Timeframe("1m"),
        aggregate_timeframes=(Timeframe("5m"),),
    )
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")

    bars = []
    for minute in range(10):
        close_timestamp = datetime(2026, 1, 1, 0, minute + 1, tzinfo=UTC)
        bars.append(
            BarCloseEvent(
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
        )

    seeded = engine.seed_source_bars(tuple(bars))

    assert seeded == 10
    helper_window = engine.market_store.window(symbol=symbol, venue=venue, timeframe=Timeframe("5m"))
    assert len(helper_window) == 1
    assert helper_window[0].bar_open_time == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)


def test_market_data_engine_can_seed_helper_timeframe_directly() -> None:
    engine = MarketDataEngine.from_timeframes(
        source_timeframe=Timeframe("1m"),
        aggregate_timeframes=(Timeframe("5m"),),
    )
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    helper_bars = (
        BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("5m"),
            bar_open_time=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            open_price=Price("100"),
            high_price=Price("105"),
            low_price=Price("99"),
            close_price=Price("104"),
            volume=Quantity("5"),
            timestamp=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        ),
        BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("5m"),
            bar_open_time=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
            open_price=Price("104"),
            high_price=Price("108"),
            low_price=Price("103"),
            close_price=Price("107"),
            volume=Quantity("6"),
            timestamp=datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
        ),
    )

    seeded = engine.seed_timeframe_bars(timeframe=Timeframe("5m"), events=helper_bars)

    assert seeded == 2
    window = engine.market_store.window(symbol=symbol, venue=venue, timeframe=Timeframe("5m"))
    assert len(window) == 2
    assert window[-1].close_price.value == 107

from datetime import UTC, datetime

from qcore.data.aggregation import TimeframeBarAggregator
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def test_timeframe_aggregator_emits_higher_timeframe_bar_after_boundary() -> None:
    aggregator = TimeframeBarAggregator(
        source_timeframe=Timeframe("1m"),
        output_timeframes=(Timeframe("5m"),),
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
        emitted.extend(aggregator.on_bar_close(event))

    assert len(emitted) == 1
    assert emitted[0].timeframe == Timeframe("5m")
    assert emitted[0].bar_open_time == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert emitted[0].timestamp == datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    assert emitted[0].volume.value == 5

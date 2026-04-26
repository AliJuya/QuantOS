from datetime import UTC, datetime

from qcore.data.ingestion import IncrementalEventBarBuilder
from qcore.domain.events import TickEvent, TradeEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def test_trade_event_bar_builder_emits_source_bar_after_boundary() -> None:
    builder = IncrementalEventBarBuilder(source_timeframe=Timeframe("1m"), input_mode="trades")
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")

    builder.on_trade(TradeEvent(symbol=symbol, venue=venue, price=Price("100"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)))
    builder.on_trade(TradeEvent(symbol=symbol, venue=venue, price=Price("101"), quantity=Quantity("2"), timestamp=datetime(2026, 1, 1, 0, 0, 40, tzinfo=UTC)))
    builder.on_trade(TradeEvent(symbol=symbol, venue=venue, price=Price("102"), quantity=Quantity("1"), timestamp=datetime(2026, 1, 1, 0, 1, 5, tzinfo=UTC)))
    builder.on_trade(TradeEvent(symbol=symbol, venue=venue, price=Price("103"), quantity=Quantity("3"), timestamp=datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC)))
    emitted = builder.on_trade(
        TradeEvent(symbol=symbol, venue=venue, price=Price("104"), quantity=Quantity("4"), timestamp=datetime(2026, 1, 1, 0, 2, 1, tzinfo=UTC))
    )

    assert len(emitted) == 1
    bar = emitted[0]
    assert bar.bar_open_time == datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)
    assert bar.timestamp == datetime(2026, 1, 1, 0, 2, 0, tzinfo=UTC)
    assert bar.open_price.value == 102
    assert bar.high_price.value == 103
    assert bar.low_price.value == 102
    assert bar.close_price.value == 103
    assert bar.volume.value == 4


def test_tick_event_bar_builder_uses_mid_price() -> None:
    builder = IncrementalEventBarBuilder(source_timeframe=Timeframe("1m"), input_mode="ticks")
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")

    builder.on_tick(TickEvent(symbol=symbol, venue=venue, bid=Price("100"), ask=Price("102"), timestamp=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)))
    builder.on_tick(TickEvent(symbol=symbol, venue=venue, bid=Price("101"), ask=Price("103"), timestamp=datetime(2026, 1, 1, 0, 1, 10, tzinfo=UTC)))
    emitted = builder.on_tick(
        TickEvent(symbol=symbol, venue=venue, bid=Price("104"), ask=Price("106"), timestamp=datetime(2026, 1, 1, 0, 2, 5, tzinfo=UTC))
    )

    assert len(emitted) == 1
    assert emitted[0].open_price.value == 102
    assert emitted[0].close_price.value == 102
    assert emitted[0].volume.value == 0

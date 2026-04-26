from datetime import UTC, datetime
from decimal import Decimal

from qcore.data.calendars import SessionWindow, WindowedSessionCalendar
from qcore.domain.enums import OrderSide
from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.ids import FillId, OrderId, StrategyId
from qcore.domain.types import ExitPolicy, Money, Price, Quantity, Symbol, Timeframe, TrailingStopPolicy, Venue
from qcore.execution.fills import BracketExitEngine


def _fill(
    *,
    fill_id: str,
    order_id: str,
    symbol: Symbol,
    venue: Venue,
    side: OrderSide,
    timestamp: datetime,
    quantity: str = "1",
    price: str = "100",
    strategy_id: str,
    target_quantity: str,
    exit_policy: ExitPolicy | None = None,
) -> FillEvent:
    return FillEvent(
        fill_id=FillId(fill_id),
        order_id=OrderId(order_id),
        symbol=symbol,
        side=side,
        quantity=Quantity(quantity),
        fill_price=Price(price),
        venue=venue,
        timestamp=timestamp,
        fee=Money("0"),
        slippage_bps=Decimal("0"),
        strategy_id=StrategyId(strategy_id),
        exit_policy=exit_policy,
        metadata={"target_quantity": target_quantity},
    )


def _bar(
    *,
    symbol: Symbol,
    venue: Venue,
    timestamp: datetime,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    timeframe: str = "1m",
) -> BarCloseEvent:
    tf = Timeframe(timeframe)
    return BarCloseEvent(
        symbol=symbol,
        venue=venue,
        timeframe=tf,
        bar_open_time=timestamp - tf.duration,
        open_price=Price(open_price),
        high_price=Price(high_price),
        low_price=Price(low_price),
        close_price=Price(close_price),
        volume=Quantity("10"),
        timestamp=timestamp,
    )


def test_bracket_exit_engine_emits_stop_first_when_both_hit() -> None:
    symbol = Symbol("ETHUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"), intrabar_exit_policy="stop_first")
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-1",
            order_id="order-1",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="s1",
            target_quantity="1",
            exit_policy=ExitPolicy(stop_loss=Price("99"), take_profit=Price("101")),
        )
    )

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="101.5",
            low_price="98.5",
            close_price="100.5",
        )
    )

    assert len(orders) == 1
    assert orders[0].side is OrderSide.SELL
    assert orders[0].metadata["exit_reason"] == "STOP_LOSS"
    assert orders[0].metadata["forced_fill_price"] == "99"


def test_bracket_exit_engine_emits_take_profit_for_short() -> None:
    symbol = Symbol("ETHUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"), intrabar_exit_policy="stop_first")
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-2",
            order_id="order-2",
            symbol=symbol,
            venue=venue,
            side=OrderSide.SELL,
            timestamp=ts,
            quantity="2",
            strategy_id="s2",
            target_quantity="-2",
            exit_policy=ExitPolicy(stop_loss=Price("101"), take_profit=Price("98")),
        )
    )

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="100.2",
            low_price="97.8",
            close_price="98.2",
        )
    )

    assert len(orders) == 1
    assert orders[0].side is OrderSide.BUY
    assert orders[0].metadata["exit_reason"] == "TAKE_PROFIT"
    assert orders[0].metadata["forced_fill_price"] == "98"


def test_bracket_exit_engine_keeps_same_symbol_strategies_isolated() -> None:
    symbol = Symbol("ETHUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"))
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-long",
            order_id="order-long",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="long_s",
            target_quantity="1",
            exit_policy=ExitPolicy(stop_loss=Price("95"), take_profit=Price("110")),
        )
    )
    engine.on_fill(
        _fill(
            fill_id="fill-short",
            order_id="order-short",
            symbol=symbol,
            venue=venue,
            side=OrderSide.SELL,
            timestamp=ts,
            strategy_id="short_s",
            target_quantity="-1",
            exit_policy=ExitPolicy(stop_loss=Price("102"), take_profit=Price("98")),
        )
    )

    first_orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="100.3",
            low_price="97.9",
            close_price="98.1",
        )
    )

    assert len(first_orders) == 1
    assert first_orders[0].strategy_id == StrategyId("short_s")
    assert first_orders[0].metadata["exit_reason"] == "TAKE_PROFIT"

    second_orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + (Timeframe("1m").duration * 2),
            open_price="98.1",
            high_price="98.4",
            low_price="94.8",
            close_price="95.2",
        )
    )

    assert len(second_orders) == 1
    assert second_orders[0].strategy_id == StrategyId("long_s")
    assert second_orders[0].metadata["exit_reason"] == "STOP_LOSS"


def test_bracket_exit_engine_supports_trailing_stop() -> None:
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"))
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-trail",
            order_id="order-trail",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="trail_s",
            target_quantity="1",
            exit_policy=ExitPolicy(trailing_stop=TrailingStopPolicy(trail_fraction=Decimal("0.02"))),
        )
    )

    assert engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="103",
            low_price="100.5",
            close_price="102.5",
        )
    ) == []

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + (Timeframe("1m").duration * 2),
            open_price="102.5",
            high_price="102.8",
            low_price="100.8",
            close_price="101.2",
        )
    )

    assert len(orders) == 1
    assert orders[0].metadata["exit_reason"] == "TRAILING_STOP"
    assert orders[0].metadata["forced_fill_price"] == "100.94"


def test_bracket_exit_engine_supports_trailing_activation_amount() -> None:
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"))
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-trail-activation",
            order_id="order-trail-activation",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="trail_activation_s",
            target_quantity="1",
            exit_policy=ExitPolicy(
                trailing_stop=TrailingStopPolicy(
                    trail_amount=Decimal("2"),
                    activation_amount=Decimal("3"),
                )
            ),
        )
    )

    assert engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="102.5",
            low_price="99.8",
            close_price="102",
        )
    ) == []

    assert engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + (Timeframe("1m").duration * 2),
            open_price="102",
            high_price="103.4",
            low_price="101.6",
            close_price="103",
        )
    ) == []

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + (Timeframe("1m").duration * 3),
            open_price="103",
            high_price="103.1",
            low_price="101.2",
            close_price="101.5",
        )
    )

    assert len(orders) == 1
    assert orders[0].metadata["exit_reason"] == "TRAILING_STOP"
    assert orders[0].metadata["forced_fill_price"] == "101.4"


def test_bracket_exit_engine_supports_time_stop() -> None:
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    engine = BracketExitEngine(source_timeframe=Timeframe("1m"))
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-time",
            order_id="order-time",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="time_s",
            target_quantity="1",
            exit_policy=ExitPolicy(max_hold_bars=2),
        )
    )

    assert engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + Timeframe("1m").duration,
            open_price="100",
            high_price="101",
            low_price="99.8",
            close_price="100.4",
        )
    ) == []

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=ts + (Timeframe("1m").duration * 2),
            open_price="100.4",
            high_price="100.7",
            low_price="100.1",
            close_price="100.2",
        )
    )

    assert len(orders) == 1
    assert orders[0].metadata["exit_reason"] == "TIME_STOP"
    assert orders[0].metadata["forced_fill_price"] == "100.2"


def test_bracket_exit_engine_supports_session_close() -> None:
    symbol = Symbol("AAPL")
    venue = Venue("SIM")
    calendar = WindowedSessionCalendar(
        calendar_id="ny",
        timezone_name="UTC",
        session_windows=(SessionWindow(label="rth", start_hour=9, end_hour=11),),
    )
    engine = BracketExitEngine(source_timeframe=Timeframe("1h"), calendar=calendar)
    ts = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    engine.on_fill(
        _fill(
            fill_id="fill-session",
            order_id="order-session",
            symbol=symbol,
            venue=venue,
            side=OrderSide.BUY,
            timestamp=ts,
            strategy_id="session_s",
            target_quantity="1",
            exit_policy=ExitPolicy(exit_on_session_close=True),
        )
    )

    orders = engine.on_bar_close(
        _bar(
            symbol=symbol,
            venue=venue,
            timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            open_price="100",
            high_price="101",
            low_price="99.5",
            close_price="100.7",
            timeframe="1h",
        )
    )

    assert len(orders) == 1
    assert orders[0].metadata["exit_reason"] == "SESSION_CLOSE"
    assert orders[0].metadata["forced_fill_price"] == "100.7"

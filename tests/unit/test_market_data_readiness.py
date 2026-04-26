from datetime import UTC, datetime

from qcore.alpha.strategies import EmaCrossStrategy
from qcore.data import MarketDataEngine
from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import StrategyId
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def test_market_data_engine_reports_readiness_against_registered_warmup() -> None:
    symbol = Symbol("BTCUSDT")
    venue = Venue("SIM")
    strategy = EmaCrossStrategy(
        strategy_id=StrategyId("ema-cross"),
        short_period=2,
        long_period=4,
        signal_horizon=Timeframe("1d"),
        input_timeframe=Timeframe("1d"),
    )
    engine = MarketDataEngine.from_requirements(
        source_timeframe=Timeframe("1d"),
        component_requirements=(strategy,),
    )

    for i in range(3):
        ts = datetime(2026, 1, i + 1, tzinfo=UTC)
        engine.on_bar_close(
            BarCloseEvent(
                symbol=symbol,
                venue=venue,
                timeframe=Timeframe("1d"),
                bar_open_time=ts - Timeframe("1d").duration,
                open_price=Price(100 + i),
                high_price=Price(101 + i),
                low_price=Price(99 + i),
                close_price=Price(100 + i),
                volume=Quantity("1"),
                timestamp=ts,
            )
        )

    assert engine.is_ready(symbol=symbol, venue=venue, timeframe=Timeframe("1d")) is False

    ts = datetime(2026, 1, 4, tzinfo=UTC)
    engine.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("1d"),
            bar_open_time=ts - Timeframe("1d").duration,
            open_price=Price(103),
            high_price=Price(104),
            low_price=Price(102),
            close_price=Price(103),
            volume=Quantity("1"),
            timestamp=ts,
        )
    )

    assert engine.is_ready(symbol=symbol, venue=venue, timeframe=Timeframe("1d")) is True
    readiness = engine.readiness(symbol=symbol, venue=venue)
    assert readiness["1d"]["required"] == 4
    assert readiness["1d"]["seen"] == 4
    assert readiness["1d"]["ready"] is True

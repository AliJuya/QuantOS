from decimal import Decimal

from qcore.alpha.strategies import EmaCrossStrategy
from qcore.data import MarketDataEngine
from qcore.domain.ids import StrategyId
from qcore.domain.types import Timeframe


def test_market_data_engine_builds_from_component_requirements() -> None:
    strategy = EmaCrossStrategy(
        strategy_id=StrategyId("ema-cross"),
        short_period=3,
        long_period=8,
        signal_horizon=Timeframe("1d"),
        input_timeframe=Timeframe("5m"),
    )

    engine = MarketDataEngine.from_requirements(
        source_timeframe=Timeframe("1m"),
        component_requirements=(strategy,),
        aggregate_timeframes=(Timeframe("15m"),),
        river_maxlen=1234,
    )

    assert engine.config.source_timeframe == Timeframe("1m")
    assert engine.config.aggregate_timeframes == (Timeframe("5m"), Timeframe("15m"))
    assert engine.warmup_registry.global_bars_by_timeframe()[Timeframe("5m")] == 8
    assert engine.market_store.bar_river.maxlen == 1234

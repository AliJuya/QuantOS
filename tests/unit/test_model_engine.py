from datetime import UTC, datetime, timedelta

from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import ModelId
from qcore.domain.types import Price, Quantity, RegimeSnapshot, Symbol, Timeframe, Venue, VolatilitySnapshot
from qcore.models import ModelEngine
from qcore.models.regime import EmaTrendRegimeModel
from qcore.models.vol import EwmaVolatilityModel


def _bar(*, index: int, close: str) -> BarCloseEvent:
    close_timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index + 1)
    return BarCloseEvent(
        symbol=Symbol("BTCUSDT"),
        venue=Venue("SIM"),
        timeframe=Timeframe("1d"),
        bar_open_time=close_timestamp - Timeframe("1d").duration,
        open_price=Price(close),
        high_price=Price(close),
        low_price=Price(close),
        close_price=Price(close),
        volume=Quantity("1"),
        timestamp=close_timestamp,
    )


def test_model_engine_stores_latest_volatility_and_regime_snapshots() -> None:
    vol_model = EwmaVolatilityModel(
        model_id=ModelId("volatility.ewma"),
        timeframe=Timeframe("1d"),
        lookback=3,
    )
    regime_model = EmaTrendRegimeModel(
        model_id=ModelId("regime.ema"),
        timeframe=Timeframe("1d"),
        fast_period=2,
        slow_period=3,
    )
    engine = ModelEngine(models=(vol_model, regime_model))

    emitted: list[object] = []
    for index, close in enumerate(("100", "101", "102", "103", "104"), start=0):
        emitted.extend(engine.on_bar_close(_bar(index=index, close=close)))

    assert any(isinstance(item, VolatilitySnapshot) for item in emitted)
    assert any(isinstance(item, RegimeSnapshot) for item in emitted)

    vol = engine.view.latest_volatility(
        model_id=ModelId("volatility.ewma"),
        symbol=Symbol("BTCUSDT"),
        timeframe=Timeframe("1d"),
    )
    regime = engine.view.latest_regime(
        model_id=ModelId("regime.ema"),
        symbol=Symbol("BTCUSDT"),
        timeframe=Timeframe("1d"),
    )

    assert vol is not None and vol.ready is True
    assert regime is not None and regime.ready is True
    assert regime.regime == "bull"

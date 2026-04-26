from datetime import UTC, datetime
from decimal import Decimal

from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.ids import AlphaId, StrategyId
from qcore.domain.types import AlphaSignal, Money, Price, Quantity, Symbol, Timeframe


def test_value_objects_hold_decimal_and_utc_data() -> None:
    signal = AlphaSignal(
        alpha_id=AlphaId("alpha-1"),
        strategy_id=StrategyId("strategy-1"),
        symbol=Symbol("BTCUSDT"),
        side=SignalSide.LONG,
        confidence=0.75,
        horizon=Timeframe("1d"),
        entry_style=EntryStyle.TREND,
        thesis="trend",
        invalidation="reverse",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        features_ref=None,
        metadata={"ema": "100"},
    )
    money = Money(Decimal("100.50"))
    quantity = Quantity("1.25")
    price = Price("101.10")

    assert signal.timestamp.tzinfo is UTC
    assert money.amount == Decimal("100.50")
    assert quantity.value == Decimal("1.25")
    assert price.value == Decimal("101.10")


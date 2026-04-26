from datetime import UTC, datetime
from decimal import Decimal

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import AlphaId, GateId, StrategyId
from qcore.domain.results import GateDecision
from qcore.domain.types import AlphaSignal, Price, Quantity, Symbol, Timeframe, Venue
from qcore.portfolio.construction import TargetBuilder


def test_target_builder_honors_position_size_override() -> None:
    market_store = MarketStore()
    symbol = Symbol("ETHUSDT")
    venue = Venue("SIM")
    market_store.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe("1m"),
            bar_open_time=datetime(2026, 1, 1, tzinfo=UTC),
            open_price=Price("100"),
            high_price=Price("100"),
            low_price=Price("100"),
            close_price=Price("100"),
            volume=Quantity("1"),
            timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        )
    )
    accounting = AccountingEngine(market_store=market_store, starting_cash=Decimal("100000"))
    builder = TargetBuilder(
        accounting=accounting,
        market_store=market_store,
        target_notional_fraction=Decimal("0.5"),
        quantity_step=Decimal("0.0001"),
    )
    signal = AlphaSignal(
        alpha_id=AlphaId("alpha-1"),
        strategy_id=StrategyId("s1"),
        symbol=symbol,
        side=SignalSide.LONG,
        confidence=1.0,
        horizon=Timeframe("1m"),
        entry_style=EntryStyle.TREND,
        thesis="test",
        invalidation="test",
        timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        features_ref=None,
        metadata={"position_size": "1"},
    )
    target = builder.on_gate_decision(
        GateDecision(
            gate_id=GateId("gate-1"),
            alpha_id=signal.alpha_id,
            approved_signal=signal,
            reason="approved",
            timestamp=signal.timestamp,
        )
    )

    assert target is not None
    assert target.target_quantity.value == Decimal("1.0000")

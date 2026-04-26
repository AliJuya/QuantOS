from datetime import UTC, datetime
from decimal import Decimal

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.ids import AlphaId, TargetId
from qcore.domain.types import PortfolioTarget, Price, Quantity, Symbol
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Timeframe, Venue
from qcore.risk.pre_trade import BasicRiskManager


def test_risk_rejects_excessive_position_size() -> None:
    market_store = MarketStore()
    symbol = Symbol("BTCUSDT")
    market_store.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=Venue("SIM"),
            timeframe=Timeframe("1d"),
            bar_open_time=datetime(2026, 1, 1, tzinfo=UTC) - Timeframe("1d").duration,
            open_price=Price("100"),
            high_price=Price("100"),
            low_price=Price("100"),
            close_price=Price("100"),
            volume=Quantity("1"),
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    accounting = AccountingEngine(market_store=market_store, starting_cash=Decimal("100000"))
    manager = BasicRiskManager(
        accounting=accounting,
        market_store=market_store,
        max_abs_position_quantity=Decimal("1"),
        max_abs_notional=Decimal("1000"),
    )
    target = PortfolioTarget(
        target_id=TargetId("target-1"),
        alpha_id=AlphaId("alpha-1"),
        symbol=symbol,
        target_quantity=Quantity("2"),
        target_price=Price("100"),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metadata={},
    )

    decision = manager.on_portfolio_target(target)

    assert decision.approved is False
    assert decision.reason == "position limit exceeded"

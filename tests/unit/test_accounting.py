from datetime import UTC, datetime
from decimal import Decimal

from qcore.accounting.portfolio_state import AccountingEngine
from qcore.data.stores import MarketStore
from qcore.domain.enums import OrderSide
from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.ids import FillId, OrderId
from qcore.domain.types import Money, Price, Quantity, Symbol, Timeframe, Venue


def test_accounting_tracks_cash_positions_and_pnl() -> None:
    market_store = MarketStore()
    accounting = AccountingEngine(market_store=market_store, starting_cash=Decimal("1000"))
    symbol = Symbol("BTCUSDT")
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    market_store.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=Venue("SIM"),
            timeframe=Timeframe("1d"),
            bar_open_time=ts - Timeframe("1d").duration,
            open_price=Price("100"),
            high_price=Price("100"),
            low_price=Price("100"),
            close_price=Price("100"),
            volume=Quantity("1"),
            timestamp=ts,
        )
    )

    accounting.on_fill(
        FillEvent(
            fill_id=FillId("fill-1"),
            order_id=OrderId("order-1"),
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=Quantity("2"),
            fill_price=Price("100"),
            venue=Venue("SIM"),
            timestamp=ts,
            fee=Money("1"),
            slippage_bps=Decimal("0"),
        )
    )
    market_store.on_bar_close(
        BarCloseEvent(
            symbol=symbol,
            venue=Venue("SIM"),
            timeframe=Timeframe("1d"),
            bar_open_time=datetime(2026, 1, 2, tzinfo=UTC) - Timeframe("1d").duration,
            open_price=Price("110"),
            high_price=Price("110"),
            low_price=Price("110"),
            close_price=Price("110"),
            volume=Quantity("1"),
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    snapshot = accounting.mark_to_market(datetime(2026, 1, 2, tzinfo=UTC))

    assert accounting.cash_amount == Decimal("799")
    assert snapshot.balance.equity.amount == Decimal("1019")
    assert snapshot.unrealized_pnl.amount == Decimal("20")

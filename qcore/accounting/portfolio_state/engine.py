from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from qcore.accounting.positions import StrategyPositionBook
from qcore.data.stores import MarketStore
from qcore.domain.events import FillEvent
from qcore.domain.ids import EntryId
from qcore.domain.ids import StrategyId
from qcore.domain.types import (
    BalanceSnapshot,
    LedgerEntry,
    Money,
    PortfolioSnapshot,
    Symbol,
    to_decimal,
)


@dataclass(slots=True)
class AccountingEngine:
    market_store: MarketStore
    starting_cash: Decimal
    base_currency: str = "USD"
    cash_amount: Decimal = field(init=False)
    fees_paid: Decimal = field(init=False, default=Decimal("0"))
    position_book: StrategyPositionBook = field(init=False)
    ledger_sequence: int = field(default=0)

    def __post_init__(self) -> None:
        self.starting_cash = to_decimal(self.starting_cash)
        self.cash_amount = self.starting_cash
        self.position_book = StrategyPositionBook(base_currency=self.base_currency)

    def position_quantity(self, symbol: Symbol, strategy_id: str | StrategyId | None = None) -> Decimal:
        return self.position_book.position_quantity(symbol, strategy_id=strategy_id)

    def equity_amount(self) -> Decimal:
        return self.cash_amount + self.position_book.total_market_value(self.market_store)

    def on_fill(self, fill: FillEvent) -> list[object]:
        key, closed_trades, realized_delta = self.position_book.apply_fill(fill)
        signed_quantity = fill.signed_quantity
        fill_price = fill.fill_price.value

        self.cash_amount -= signed_quantity * fill_price
        self.cash_amount -= fill.fee.amount
        self.fees_paid += fill.fee.amount

        self.ledger_sequence += 1
        ledger_entry = LedgerEntry(
            entry_id=EntryId(f"ledger-{self.ledger_sequence:08d}"),
            timestamp=fill.timestamp,
            symbol=fill.symbol,
            entry_type="FILL",
            amount=Money(-(signed_quantity * fill_price) - fill.fee.amount, self.base_currency),
            cash_after=Money(self.cash_amount, self.base_currency),
            realized_pnl_after=Money(self.total_realized_pnl(), self.base_currency),
            fee=fill.fee,
            metadata={
                "strategy_id": None if key.strategy_id is None else str(key.strategy_id),
                "fill_id": str(fill.fill_id),
                "signed_quantity": str(signed_quantity),
                "fill_price": str(fill_price),
                "realized_delta": str(realized_delta),
                "trade_ids": [str(trade.trade_id) for trade in closed_trades],
                "fill_metadata": dict(fill.metadata),
            },
        )
        return [ledger_entry, *closed_trades]

    def mark_to_market(self, timestamp: datetime) -> PortfolioSnapshot:
        positions = self.position_book.aggregate_snapshots(
            self.market_store,
            timestamp=timestamp,
            base_currency=self.base_currency,
        )
        unrealized = sum((position.unrealized_pnl.amount for position in positions), start=Decimal("0"))
        realized = self.total_realized_pnl()
        equity = self.cash_amount + sum((position.market_value.amount for position in positions), start=Decimal("0"))
        balance = BalanceSnapshot(
            cash=Money(self.cash_amount, self.base_currency),
            equity=Money(equity, self.base_currency),
            fees_paid=Money(self.fees_paid, self.base_currency),
            timestamp=timestamp,
        )
        return PortfolioSnapshot(
            timestamp=timestamp,
            positions=tuple(positions),
            balance=balance,
            realized_pnl=Money(realized, self.base_currency),
            unrealized_pnl=Money(unrealized, self.base_currency),
            net_pnl=Money(realized + unrealized - self.fees_paid, self.base_currency),
        )

    def total_realized_pnl(self) -> Decimal:
        return self.position_book.total_realized_pnl()

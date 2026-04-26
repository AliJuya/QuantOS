from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from qcore.data.stores import MarketStore
from qcore.domain.enums import OrderSide, SignalSide
from qcore.domain.events import FillEvent
from qcore.domain.ids import StrategyId, TradeId
from qcore.domain.types import ClosedTrade, Money, PositionSnapshot, Price, Quantity, Symbol, Venue


@dataclass(frozen=True, slots=True)
class StrategyPositionKey:
    strategy_id: StrategyId | None
    symbol: Symbol
    venue: Venue


@dataclass(slots=True)
class OpenLot:
    side: SignalSide
    quantity: Decimal
    entry_price: Decimal
    opened_at: datetime
    entry_fee: Decimal = Decimal("0")


@dataclass(slots=True)
class StrategyPositionState:
    open_lots: list[OpenLot] = field(default_factory=list)
    realized_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")

    def quantity(self) -> Decimal:
        total = Decimal("0")
        for lot in self.open_lots:
            total += lot.quantity if lot.side is SignalSide.LONG else -lot.quantity
        return total

    def avg_price(self) -> Decimal | None:
        if not self.open_lots:
            return None
        total_qty = sum((lot.quantity for lot in self.open_lots), start=Decimal("0"))
        if total_qty == 0:
            return None
        total_notional = sum((lot.quantity * lot.entry_price for lot in self.open_lots), start=Decimal("0"))
        return total_notional / total_qty


@dataclass(slots=True)
class StrategyPositionBook:
    base_currency: str = "USD"
    positions: dict[StrategyPositionKey, StrategyPositionState] = field(default_factory=dict)
    trade_sequence: int = 0

    def apply_fill(self, fill: FillEvent) -> tuple[StrategyPositionKey, list[ClosedTrade], Decimal]:
        key = StrategyPositionKey(
            strategy_id=fill.strategy_id or _strategy_id_from_metadata(fill.metadata),
            symbol=fill.symbol,
            venue=fill.venue,
        )
        state = self.positions.setdefault(key, StrategyPositionState())
        state.fees_paid += fill.fee.amount

        fill_side = SignalSide.LONG if fill.side is OrderSide.BUY else SignalSide.SHORT
        fill_price = fill.fill_price.value
        remaining_quantity = fill.quantity.value
        total_fill_quantity = fill.quantity.value
        realized_total = Decimal("0")
        closed_trades: list[ClosedTrade] = []

        while remaining_quantity > 0 and state.open_lots and state.open_lots[0].side is not fill_side:
            lot = state.open_lots[0]
            lot_quantity_before = lot.quantity
            matched_quantity = min(lot_quantity_before, remaining_quantity)
            entry_fee_share = (
                lot.entry_fee * matched_quantity / lot_quantity_before
                if lot_quantity_before > 0
                else Decimal("0")
            )
            closing_fee_share = (
                fill.fee.amount * matched_quantity / total_fill_quantity
                if total_fill_quantity > 0
                else Decimal("0")
            )
            lot.entry_fee -= entry_fee_share

            realized_pnl = (
                matched_quantity * (fill_price - lot.entry_price)
                if lot.side is SignalSide.LONG
                else matched_quantity * (lot.entry_price - fill_price)
            )
            realized_total += realized_pnl
            state.realized_pnl += realized_pnl

            self.trade_sequence += 1
            closed_trades.append(
                ClosedTrade(
                    trade_id=TradeId(f"trade-{self.trade_sequence:08d}"),
                    strategy_id=key.strategy_id,
                    symbol=key.symbol,
                    venue=key.venue,
                    side=lot.side,
                    quantity=Quantity(matched_quantity),
                    entry_price=Price(lot.entry_price),
                    exit_price=fill.fill_price,
                    entry_timestamp=lot.opened_at,
                    exit_timestamp=fill.timestamp,
                    realized_pnl=Money(realized_pnl, self.base_currency),
                    fees_paid=Money(entry_fee_share + closing_fee_share, self.base_currency),
                    hold_seconds=max(0, int((fill.timestamp - lot.opened_at).total_seconds())),
                    exit_reason=str(fill.metadata.get("exit_reason")) if fill.metadata.get("exit_reason") is not None else None,
                    metadata={
                        "fill_id": str(fill.fill_id),
                        "order_id": str(fill.order_id),
                    },
                )
            )

            if matched_quantity == lot_quantity_before:
                state.open_lots.pop(0)
            else:
                lot.quantity -= matched_quantity
            remaining_quantity -= matched_quantity

        if remaining_quantity > 0:
            entry_fee_share = (
                fill.fee.amount * remaining_quantity / total_fill_quantity
                if total_fill_quantity > 0
                else Decimal("0")
            )
            state.open_lots.append(
                OpenLot(
                    side=fill_side,
                    quantity=remaining_quantity,
                    entry_price=fill_price,
                    opened_at=fill.timestamp,
                    entry_fee=entry_fee_share,
                )
            )

        return key, closed_trades, realized_total

    def position_quantity(self, symbol: Symbol, strategy_id: str | StrategyId | None = None) -> Decimal:
        requested_strategy = _coerce_strategy_id(strategy_id)
        total = Decimal("0")
        for key, state in self.positions.items():
            if key.symbol != symbol:
                continue
            if requested_strategy is not None and key.strategy_id != requested_strategy:
                continue
            total += state.quantity()
        return total

    def total_market_value(self, market_store: MarketStore) -> Decimal:
        total = Decimal("0")
        for key, state in self.positions.items():
            mark = market_store.price_for(key.symbol)
            if mark is None:
                continue
            total += state.quantity() * mark.value
        return total

    def total_realized_pnl(self) -> Decimal:
        return sum((state.realized_pnl for state in self.positions.values()), start=Decimal("0"))

    def aggregate_snapshots(
        self,
        market_store: MarketStore,
        timestamp: datetime,
        base_currency: str,
    ) -> tuple[PositionSnapshot, ...]:
        grouped: dict[Symbol, list[tuple[StrategyPositionKey, StrategyPositionState]]] = {}
        for key, state in self.positions.items():
            if not state.open_lots:
                continue
            grouped.setdefault(key.symbol, []).append((key, state))

        snapshots: list[PositionSnapshot] = []
        for symbol, entries in sorted(grouped.items(), key=lambda item: item[0].value):
            mark = market_store.price_for(symbol)
            mark_value = mark.value if mark is not None else None
            net_quantity = Decimal("0")
            market_value = Decimal("0")
            unrealized_pnl = Decimal("0")
            realized_pnl = Decimal("0")
            weighted_abs_notional = Decimal("0")
            weighted_abs_qty = Decimal("0")
            sides: set[SignalSide] = set()

            for _, state in entries:
                qty = state.quantity()
                avg_price = state.avg_price()
                realized_pnl += state.realized_pnl
                net_quantity += qty
                if avg_price is not None:
                    sides.add(SignalSide.LONG if qty > 0 else SignalSide.SHORT)
                    weighted_abs_notional += abs(qty) * avg_price
                    weighted_abs_qty += abs(qty)
                    if mark_value is not None:
                        market_value += qty * mark_value
                        unrealized_pnl += (
                            qty * (mark_value - avg_price)
                            if qty > 0
                            else abs(qty) * (avg_price - mark_value)
                        )

            aggregate_avg_price: Price | None = None
            if net_quantity != 0 and len(sides) <= 1 and weighted_abs_qty > 0:
                aggregate_avg_price = Price(weighted_abs_notional / weighted_abs_qty)

            snapshots.append(
                PositionSnapshot(
                    symbol=symbol,
                    quantity=Quantity(net_quantity),
                    avg_price=aggregate_avg_price,
                    mark_price=Price(mark_value) if mark_value is not None and mark_value > 0 else None,
                    market_value=Money(market_value, base_currency),
                    unrealized_pnl=Money(unrealized_pnl, base_currency),
                    realized_pnl=Money(realized_pnl, base_currency),
                    timestamp=timestamp,
                )
            )
        return tuple(snapshots)


def _coerce_strategy_id(value: str | StrategyId | None) -> StrategyId | None:
    if value is None:
        return None
    if isinstance(value, StrategyId):
        return value
    text = str(value).strip()
    if not text:
        return None
    return StrategyId(text)


def _strategy_id_from_metadata(metadata: Mapping[str, Any]) -> StrategyId | None:
    raw = metadata.get("strategy_id")
    return _coerce_strategy_id(raw)

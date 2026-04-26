from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from qcore.data.calendars import AlwaysOpenCalendar, TradingCalendarProtocol
from qcore.domain.commands import OrderRequest
from qcore.domain.enums import OrderSide, OrderType, SignalSide, TimeInForce
from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.ids import InstructionId, OrderId, StrategyId
from qcore.domain.types import ExitPolicy, Price, Quantity, Timeframe, TrailingStopPolicy, Symbol, Venue, to_decimal


@dataclass(frozen=True, slots=True)
class ManagedPositionKey:
    strategy_id: StrategyId | None
    symbol: Symbol
    venue: Venue


@dataclass(slots=True)
class ManagedPosition:
    key: ManagedPositionKey
    side: SignalSide
    quantity: Decimal
    entry_price: Decimal
    opened_at: datetime
    bars_held: int
    best_price: Decimal
    exit_policy: ExitPolicy


@dataclass(frozen=True, slots=True)
class ExitHit:
    reason: str
    fill_price: Decimal


@dataclass(slots=True)
class ManagedExitEngine:
    source_timeframe: Timeframe
    calendar: TradingCalendarProtocol = field(default_factory=AlwaysOpenCalendar)
    intrabar_exit_policy: str = "stop_first"
    order_sequence: int = 0
    positions: dict[ManagedPositionKey, ManagedPosition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        policy = str(self.intrabar_exit_policy).strip().lower()
        if policy not in {"stop_first", "tp_first"}:
            raise ValueError("intrabar_exit_policy must be 'stop_first' or 'tp_first'")
        self.intrabar_exit_policy = policy

    def on_fill(self, fill: FillEvent) -> None:
        key = ManagedPositionKey(
            strategy_id=fill.strategy_id or _strategy_id_from_metadata(fill.metadata),
            symbol=fill.symbol,
            venue=fill.venue,
        )
        target_quantity = _optional_decimal(fill.metadata.get("target_quantity"))
        if target_quantity is not None and target_quantity == 0:
            self.positions.pop(key, None)
            return None

        exit_policy = fill.exit_policy or _legacy_exit_policy(fill.metadata.get("execution_plan"))
        if exit_policy is None:
            if target_quantity is not None:
                self.positions.pop(key, None)
            return None

        if target_quantity is None:
            target_quantity = fill.signed_quantity
        if target_quantity == 0:
            self.positions.pop(key, None)
            return None

        side = SignalSide.LONG if target_quantity > 0 else SignalSide.SHORT
        existing = self.positions.get(key)
        if existing is not None and existing.side is side:
            entry_price = existing.entry_price
            opened_at = existing.opened_at
            bars_held = existing.bars_held
            if side is SignalSide.LONG:
                best_price = max(existing.best_price, fill.fill_price.value)
            else:
                best_price = min(existing.best_price, fill.fill_price.value)
        else:
            entry_price = fill.fill_price.value
            opened_at = fill.timestamp
            bars_held = 0
            best_price = fill.fill_price.value

        self.positions[key] = ManagedPosition(
            key=key,
            side=side,
            quantity=abs(target_quantity),
            entry_price=entry_price,
            opened_at=opened_at,
            bars_held=bars_held,
            best_price=best_price,
            exit_policy=exit_policy,
        )
        return None

    def on_bar_close(self, event: BarCloseEvent) -> list[OrderRequest]:
        if event.timeframe != self.source_timeframe:
            return []

        emitted: list[OrderRequest] = []
        matching_keys = [
            key
            for key in self.positions
            if key.symbol == event.symbol and key.venue == event.venue
        ]
        for key in matching_keys:
            position = self.positions.get(key)
            if position is None:
                continue
            price_hit = self._check_price_hit(position, event)
            if price_hit is not None:
                self.positions.pop(key, None)
                emitted.append(self._build_exit_order(position, event, price_hit))
                continue

            position.bars_held += 1
            position.best_price = self._updated_best_price(position, event)

            close_hit = self._check_close_hit(position, event)
            if close_hit is None:
                continue

            self.positions.pop(key, None)
            emitted.append(self._build_exit_order(position, event, close_hit))
        return emitted

    def _check_price_hit(self, position: ManagedPosition, event: BarCloseEvent) -> ExitHit | None:
        stop_candidates: list[ExitHit] = []
        bar_high = event.high_price.value
        bar_low = event.low_price.value

        if position.exit_policy.stop_loss is not None:
            stop_price = position.exit_policy.stop_loss.value
            if position.side is SignalSide.LONG and bar_low <= stop_price:
                stop_candidates.append(ExitHit("STOP_LOSS", stop_price))
            if position.side is SignalSide.SHORT and bar_high >= stop_price:
                stop_candidates.append(ExitHit("STOP_LOSS", stop_price))

        trailing_hit = self._check_trailing_hit(position, event)
        if trailing_hit is not None:
            stop_candidates.append(trailing_hit)

        take_profit_hit = self._check_take_profit_hit(position, event)
        if take_profit_hit is None:
            return stop_candidates[0] if stop_candidates else None
        if not stop_candidates:
            return take_profit_hit
        if self.intrabar_exit_policy == "tp_first":
            return take_profit_hit
        return stop_candidates[0]

    def _check_take_profit_hit(self, position: ManagedPosition, event: BarCloseEvent) -> ExitHit | None:
        take_profit = position.exit_policy.take_profit
        if take_profit is None:
            return None
        tp_price = take_profit.value
        if position.side is SignalSide.LONG and event.high_price.value >= tp_price:
            return ExitHit("TAKE_PROFIT", tp_price)
        if position.side is SignalSide.SHORT and event.low_price.value <= tp_price:
            return ExitHit("TAKE_PROFIT", tp_price)
        return None

    def _check_trailing_hit(self, position: ManagedPosition, event: BarCloseEvent) -> ExitHit | None:
        trailing = position.exit_policy.trailing_stop
        if trailing is None:
            return None
        if not _trailing_activated(position, trailing):
            return None
        trailing_price = _trailing_stop_price(position.side, position.best_price, trailing)
        if position.side is SignalSide.LONG and event.low_price.value <= trailing_price:
            return ExitHit("TRAILING_STOP", trailing_price)
        if position.side is SignalSide.SHORT and event.high_price.value >= trailing_price:
            return ExitHit("TRAILING_STOP", trailing_price)
        return None

    def _check_close_hit(self, position: ManagedPosition, event: BarCloseEvent) -> ExitHit | None:
        if position.exit_policy.max_hold_bars is not None and position.bars_held >= position.exit_policy.max_hold_bars:
            return ExitHit("TIME_STOP", event.close_price.value)
        if position.exit_policy.exit_on_session_close and self._is_session_close(event.timestamp):
            return ExitHit("SESSION_CLOSE", event.close_price.value)
        return None

    def _updated_best_price(self, position: ManagedPosition, event: BarCloseEvent) -> Decimal:
        if position.side is SignalSide.LONG:
            return max(position.best_price, event.high_price.value)
        return min(position.best_price, event.low_price.value)

    def _is_session_close(self, timestamp: datetime) -> bool:
        current_ctx = self.calendar.session_context(timestamp)
        next_ctx = self.calendar.session_context(timestamp + self.source_timeframe.duration)
        if not current_ctx.is_open:
            return True
        return (not next_ctx.is_open) or (next_ctx.session_label != current_ctx.session_label)

    def _build_exit_order(self, position: ManagedPosition, event: BarCloseEvent, hit: ExitHit) -> OrderRequest:
        self.order_sequence += 1
        order_side = OrderSide.SELL if position.side is SignalSide.LONG else OrderSide.BUY
        signed_current = position.quantity if position.side is SignalSide.LONG else -position.quantity
        return OrderRequest(
            order_id=OrderId(f"managed-exit-{self.order_sequence:08d}"),
            instruction_id=InstructionId(f"managed-exit-{self.order_sequence:08d}"),
            symbol=event.symbol,
            side=order_side,
            quantity=Quantity(position.quantity),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IOC,
            timestamp=event.timestamp,
            strategy_id=position.key.strategy_id,
            metadata={
                "managed_exit": True,
                "exit_reason": hit.reason,
                "forced_fill_price": str(hit.fill_price),
                "target_quantity": "0",
                "current_quantity": str(signed_current),
                "strategy_id": None if position.key.strategy_id is None else str(position.key.strategy_id),
                "source_timeframe": str(self.source_timeframe),
            },
        )


BracketExitEngine = ManagedExitEngine


def _legacy_exit_policy(value: Mapping[str, Any] | Any) -> ExitPolicy | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("execution_plan must be a mapping")
    stop_loss = _optional_decimal(value.get("stop_loss"))
    take_profit = _optional_decimal(value.get("take_profit"))
    trailing_fraction = _optional_decimal(value.get("trailing_stop_fraction"))
    trailing_amount = _optional_decimal(value.get("trailing_stop_amount"))
    trailing_activation_fraction = _optional_decimal(value.get("trailing_activation_fraction"))
    trailing_activation_amount = _optional_decimal(value.get("trailing_activation_amount"))
    max_hold_bars = value.get("max_hold_bars")
    exit_on_session_close = bool(value.get("exit_on_session_close", False))
    trailing_stop = None
    if trailing_fraction is not None or trailing_amount is not None:
        trailing_stop = TrailingStopPolicy(
            trail_fraction=trailing_fraction,
            trail_amount=trailing_amount,
            activation_fraction=trailing_activation_fraction,
            activation_amount=trailing_activation_amount,
        )
    if stop_loss is None and take_profit is None and trailing_stop is None and max_hold_bars is None and not exit_on_session_close:
        return None
    return ExitPolicy(
        stop_loss=Price(stop_loss) if stop_loss is not None else None,
        take_profit=Price(take_profit) if take_profit is not None else None,
        trailing_stop=trailing_stop,
        max_hold_bars=int(max_hold_bars) if max_hold_bars is not None else None,
        exit_on_session_close=exit_on_session_close,
    )


def _trailing_stop_price(side: SignalSide, best_price: Decimal, trailing: TrailingStopPolicy) -> Decimal:
    if trailing.trail_fraction is not None:
        if side is SignalSide.LONG:
            return best_price * (Decimal("1") - trailing.trail_fraction)
        return best_price * (Decimal("1") + trailing.trail_fraction)
    amount = trailing.trail_amount or Decimal("0")
    if side is SignalSide.LONG:
        return best_price - amount
    return best_price + amount


def _trailing_activated(position: ManagedPosition, trailing: TrailingStopPolicy) -> bool:
    if trailing.activation_fraction is None and trailing.activation_amount is None:
        return True

    if position.side is SignalSide.LONG:
        favorable_move = position.best_price - position.entry_price
    else:
        favorable_move = position.entry_price - position.best_price

    if trailing.activation_amount is not None:
        return favorable_move >= trailing.activation_amount

    threshold = position.entry_price * (trailing.activation_fraction or Decimal("0"))
    return favorable_move >= threshold


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return to_decimal(value)


def _strategy_id_from_metadata(metadata: Mapping[str, Any]) -> StrategyId | None:
    raw = metadata.get("strategy_id")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return StrategyId(value)

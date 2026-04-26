from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent
from qcore.domain.types import Price, Quantity, Timeframe


def _floor_timestamp(timestamp: datetime, frame: Timeframe) -> datetime:
    frame_seconds = int(frame.duration.total_seconds())
    floored = int(timestamp.timestamp()) // frame_seconds * frame_seconds
    return datetime.fromtimestamp(floored, tz=timestamp.tzinfo)


@dataclass(slots=True)
class _BarBucket:
    bar_open_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal


@dataclass(slots=True)
class IncrementalEventBarBuilder:
    source_timeframe: Timeframe
    input_mode: str
    _current: dict[tuple[object, object], _BarBucket] = field(default_factory=dict)
    _current_bucket_open: dict[tuple[object, object], datetime] = field(default_factory=dict)
    _can_emit: dict[tuple[object, object], bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        mode = str(self.input_mode).strip().lower()
        if mode not in {"ticks", "trades"}:
            raise ValueError("input_mode must be 'ticks' or 'trades'")
        self.input_mode = mode

    def on_tick(self, event: TickEvent) -> list[BarCloseEvent]:
        if self.input_mode != "ticks":
            return []
        mid = (event.bid.value + event.ask.value) / Decimal("2")
        return self._on_point(
            symbol=event.symbol,
            venue=event.venue,
            price=mid,
            volume=Decimal("0"),
            timestamp=event.timestamp,
        )

    def on_trade(self, event: TradeEvent) -> list[BarCloseEvent]:
        if self.input_mode != "trades":
            return []
        return self._on_point(
            symbol=event.symbol,
            venue=event.venue,
            price=event.price.value,
            volume=event.quantity.value,
            timestamp=event.timestamp,
        )

    def _on_point(self, *, symbol, venue, price: Decimal, volume: Decimal, timestamp: datetime) -> list[BarCloseEvent]:
        emitted: list[BarCloseEvent] = []
        stream_key = (symbol, venue)
        bucket_open = _floor_timestamp(timestamp, self.source_timeframe)
        current = self._current.get(stream_key)
        current_bucket_open = self._current_bucket_open.get(stream_key)

        if current is None:
            self._start_bucket(stream_key, bucket_open, price, volume)
            self._can_emit[stream_key] = False
            return emitted

        if bucket_open == current_bucket_open:
            self._update_bucket(current, price, volume)
            return emitted

        if self._can_emit.get(stream_key, False):
            emitted.append(self._to_event(symbol=symbol, venue=venue, bucket=current))
        else:
            self._can_emit[stream_key] = True

        self._start_bucket(stream_key, bucket_open, price, volume)
        return emitted

    def _start_bucket(self, stream_key: tuple[object, object], bucket_open: datetime, price: Decimal, volume: Decimal) -> None:
        self._current_bucket_open[stream_key] = bucket_open
        self._current[stream_key] = _BarBucket(
            bar_open_time=bucket_open,
            open_price=price,
            high_price=price,
            low_price=price,
            close_price=price,
            volume=volume,
        )

    @staticmethod
    def _update_bucket(bucket: _BarBucket, price: Decimal, volume: Decimal) -> None:
        bucket.high_price = max(bucket.high_price, price)
        bucket.low_price = min(bucket.low_price, price)
        bucket.close_price = price
        bucket.volume += volume

    def _to_event(self, *, symbol, venue, bucket: _BarBucket) -> BarCloseEvent:
        return BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=self.source_timeframe,
            bar_open_time=bucket.bar_open_time,
            open_price=Price(bucket.open_price),
            high_price=Price(bucket.high_price),
            low_price=Price(bucket.low_price),
            close_price=Price(bucket.close_price),
            volume=Quantity(bucket.volume),
            timestamp=bucket.bar_open_time + self.source_timeframe.duration,
        )

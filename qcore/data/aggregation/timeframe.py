from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import math

from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue


def _floor_timestamp(timestamp: datetime, frame: Timeframe) -> datetime:
    frame_seconds = int(frame.duration.total_seconds())
    floored = int(timestamp.timestamp()) // frame_seconds * frame_seconds
    return datetime.fromtimestamp(floored, tz=timestamp.tzinfo)


@dataclass(slots=True)
class _AggregateBucket:
    bar_open_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    taker_buy_quote_volume: Decimal | None = None
    taker_buy_base_volume: Decimal | None = None


def _optional_decimal(value: object) -> Decimal | None:
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return Decimal(str(numeric))


@dataclass(slots=True)
class TimeframeBarAggregator:
    source_timeframe: Timeframe
    output_timeframes: tuple[Timeframe, ...]
    _current: dict[tuple[Symbol, Venue, Timeframe], _AggregateBucket] = field(default_factory=dict)
    _current_bucket_open: dict[tuple[Symbol, Venue, Timeframe], datetime] = field(default_factory=dict)
    _can_emit: dict[tuple[Symbol, Venue, Timeframe], bool] = field(default_factory=dict)

    def on_bar_close(self, event: BarCloseEvent) -> list[BarCloseEvent]:
        if event.timeframe != self.source_timeframe:
            return []

        emitted: list[BarCloseEvent] = []
        for output_timeframe in self.output_timeframes:
            if output_timeframe.duration <= self.source_timeframe.duration:
                raise ValueError("output timeframe must be greater than source timeframe")
            if output_timeframe.duration.total_seconds() % self.source_timeframe.duration.total_seconds() != 0:
                raise ValueError("output timeframe must be an integer multiple of source timeframe")

            stream_key = (event.symbol, event.venue, output_timeframe)
            bucket_open = _floor_timestamp(event.bar_open_time, output_timeframe)
            current = self._current.get(stream_key)
            current_bucket_open = self._current_bucket_open.get(stream_key)

            if current is None:
                self._start_bucket(stream_key, bucket_open, event)
                self._can_emit.setdefault(stream_key, False)
            elif bucket_open != current_bucket_open:
                emitted.extend(
                    self._roll_bucket(
                        stream_key=stream_key,
                        symbol=event.symbol,
                        venue=event.venue,
                        timeframe=output_timeframe,
                    )
                )
                self._start_bucket(stream_key, bucket_open, event)
            else:
                self._update_bucket(current, event)

            current = self._current.get(stream_key)
            current_bucket_open = self._current_bucket_open.get(stream_key)
            if current is None or current_bucket_open is None:
                continue

            if event.timestamp >= current_bucket_open + output_timeframe.duration:
                emitted.extend(
                    self._roll_bucket(
                        stream_key=stream_key,
                        symbol=event.symbol,
                        venue=event.venue,
                        timeframe=output_timeframe,
                    )
                )

        return emitted

    def _roll_bucket(
        self,
        *,
        stream_key: tuple[Symbol, Venue, Timeframe],
        symbol: Symbol,
        venue: Venue,
        timeframe: Timeframe,
    ) -> list[BarCloseEvent]:
        current = self._current.get(stream_key)
        if current is None:
            return []

        emitted: list[BarCloseEvent] = []
        if self._can_emit.get(stream_key, False):
            emitted.append(self._to_event(symbol, venue, timeframe, current))
        else:
            self._can_emit[stream_key] = True

        self._current.pop(stream_key, None)
        self._current_bucket_open.pop(stream_key, None)
        return emitted

    def _start_bucket(
        self,
        stream_key: tuple[Symbol, Venue, Timeframe],
        bucket_open: datetime,
        event: BarCloseEvent,
    ) -> None:
        self._current_bucket_open[stream_key] = bucket_open
        quote_volume = _optional_decimal(event.metadata.get("quote_volume"))
        taker_buy_quote_volume = _optional_decimal(event.metadata.get("taker_buy_quote_volume"))
        taker_buy_base_volume = _optional_decimal(event.metadata.get("taker_buy_base_volume"))
        self._current[stream_key] = _AggregateBucket(
            bar_open_time=bucket_open,
            open_price=event.open_price.value,
            high_price=event.high_price.value,
            low_price=event.low_price.value,
            close_price=event.close_price.value,
            volume=event.volume.value,
            quote_volume=quote_volume,
            taker_buy_quote_volume=taker_buy_quote_volume,
            taker_buy_base_volume=taker_buy_base_volume,
        )

    @staticmethod
    def _update_bucket(bucket: _AggregateBucket, event: BarCloseEvent) -> None:
        bucket.high_price = max(bucket.high_price, event.high_price.value)
        bucket.low_price = min(bucket.low_price, event.low_price.value)
        bucket.close_price = event.close_price.value
        bucket.volume += event.volume.value
        quote_volume = _optional_decimal(event.metadata.get("quote_volume"))
        taker_buy_quote_volume = _optional_decimal(event.metadata.get("taker_buy_quote_volume"))
        taker_buy_base_volume = _optional_decimal(event.metadata.get("taker_buy_base_volume"))
        if quote_volume is not None:
            bucket.quote_volume = (bucket.quote_volume or Decimal("0")) + quote_volume
        if taker_buy_quote_volume is not None:
            bucket.taker_buy_quote_volume = (bucket.taker_buy_quote_volume or Decimal("0")) + taker_buy_quote_volume
        if taker_buy_base_volume is not None:
            bucket.taker_buy_base_volume = (bucket.taker_buy_base_volume or Decimal("0")) + taker_buy_base_volume

    @staticmethod
    def _to_event(symbol: Symbol, venue: Venue, timeframe: Timeframe, bucket: _AggregateBucket) -> BarCloseEvent:
        metadata: dict[str, object] = {}
        if bucket.quote_volume is not None:
            metadata["quote_volume"] = str(bucket.quote_volume)
        if bucket.taker_buy_quote_volume is not None:
            metadata["taker_buy_quote_volume"] = str(bucket.taker_buy_quote_volume)
        if bucket.taker_buy_base_volume is not None:
            metadata["taker_buy_base_volume"] = str(bucket.taker_buy_base_volume)
        return BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=timeframe,
            bar_open_time=bucket.bar_open_time,
            open_price=Price(bucket.open_price),
            high_price=Price(bucket.high_price),
            low_price=Price(bucket.low_price),
            close_price=Price(bucket.close_price),
            volume=Quantity(bucket.volume),
            timestamp=bucket.bar_open_time + timeframe.duration,
            metadata=metadata,
        )

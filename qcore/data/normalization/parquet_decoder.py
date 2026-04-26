from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from datetime import timedelta
from typing import Any, Mapping

from qcore.data.catalog import (
    ResolvedCsvBarDataset,
    ResolvedCsvTickDataset,
    ResolvedCsvTradeDataset,
    ResolvedParquetBarDataset,
    ResolvedParquetTickDataset,
    ResolvedParquetTradeDataset,
)
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent
from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue, ensure_utc


def _coerce_timestamp(value: Any) -> datetime:
    if hasattr(value, "as_py"):
        value = value.as_py()

    if isinstance(value, datetime):
        return ensure_utc(value)

    if isinstance(value, str):
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))

    if isinstance(value, (int, float, Decimal)):
        numeric = float(value)
        magnitude = abs(numeric)
        if magnitude >= 1e17:
            seconds = numeric / 1_000_000_000
        elif magnitude >= 1e14:
            seconds = numeric / 1_000_000
        elif magnitude >= 1e11:
            seconds = numeric / 1_000
        else:
            seconds = numeric
        return datetime.fromtimestamp(seconds, tz=UTC)

    raise TypeError(f"unsupported timestamp value: {value!r}")


@dataclass(frozen=True, slots=True)
class ParquetBarDecoder:
    dataset: ResolvedParquetBarDataset | ResolvedCsvBarDataset
    _default_symbol_obj: Symbol | None = field(init=False, repr=False)
    _default_venue_obj: Venue | None = field(init=False, repr=False)
    _default_timeframe_obj: Timeframe | None = field(init=False, repr=False)
    _default_timeframe_duration: timedelta | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        default_symbol = Symbol(self.dataset.default_symbol) if self.dataset.default_symbol is not None else None
        default_venue = Venue(self.dataset.default_venue) if self.dataset.default_venue is not None else None
        default_timeframe = Timeframe(self.dataset.default_timeframe) if self.dataset.default_timeframe is not None else None
        object.__setattr__(self, "_default_symbol_obj", default_symbol)
        object.__setattr__(self, "_default_venue_obj", default_venue)
        object.__setattr__(self, "_default_timeframe_obj", default_timeframe)
        object.__setattr__(
            self,
            "_default_timeframe_duration",
            None if default_timeframe is None else default_timeframe.duration,
        )

    def required_columns(self) -> tuple[str, ...]:
        columns = [
            self.dataset.columns.timestamp,
            self.dataset.columns.open,
            self.dataset.columns.high,
            self.dataset.columns.low,
            self.dataset.columns.close,
            self.dataset.columns.volume,
        ]
        if self.dataset.columns.quote_volume is not None:
            columns.append(self.dataset.columns.quote_volume)
        if self.dataset.columns.taker_buy_quote_volume is not None:
            columns.append(self.dataset.columns.taker_buy_quote_volume)
        if self.dataset.columns.taker_buy_base_volume is not None:
            columns.append(self.dataset.columns.taker_buy_base_volume)
        if self.dataset.columns.symbol is not None and self.dataset.default_symbol is None:
            columns.append(self.dataset.columns.symbol)
        if self.dataset.columns.venue is not None and self.dataset.default_venue is None:
            columns.append(self.dataset.columns.venue)
        if self.dataset.columns.timeframe is not None and self.dataset.default_timeframe is None:
            columns.append(self.dataset.columns.timeframe)
        return tuple(dict.fromkeys(columns))

    def decode_row(self, row: Mapping[str, Any]) -> BarCloseEvent:
        symbol = self._default_symbol_obj or Symbol(
            self._dimension_value(row, self.dataset.columns.symbol, self.dataset.default_symbol, "symbol")
        )
        venue = self._default_venue_obj or Venue(
            self._dimension_value(row, self.dataset.columns.venue, self.dataset.default_venue, "venue")
        )
        timeframe = self._default_timeframe_obj or Timeframe(
            self._dimension_value(row, self.dataset.columns.timeframe, self.dataset.default_timeframe, "timeframe")
        )
        timeframe_duration = self._default_timeframe_duration or timeframe.duration

        raw_timestamp = _coerce_timestamp(row[self.dataset.columns.timestamp])
        if self.dataset.timestamp_is == "open":
            bar_open_time = raw_timestamp
            close_timestamp = raw_timestamp + timeframe_duration
        else:
            close_timestamp = raw_timestamp
            bar_open_time = raw_timestamp - timeframe_duration

        metadata: dict[str, Any] = {}
        if self.dataset.columns.quote_volume is not None and self.dataset.columns.quote_volume in row:
            metadata["quote_volume"] = row[self.dataset.columns.quote_volume]
        if self.dataset.columns.taker_buy_quote_volume is not None and self.dataset.columns.taker_buy_quote_volume in row:
            metadata["taker_buy_quote_volume"] = row[self.dataset.columns.taker_buy_quote_volume]
        if self.dataset.columns.taker_buy_base_volume is not None and self.dataset.columns.taker_buy_base_volume in row:
            metadata["taker_buy_base_volume"] = row[self.dataset.columns.taker_buy_base_volume]

        return BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=timeframe,
            bar_open_time=bar_open_time,
            open_price=Price(row[self.dataset.columns.open]),
            high_price=Price(row[self.dataset.columns.high]),
            low_price=Price(row[self.dataset.columns.low]),
            close_price=Price(row[self.dataset.columns.close]),
            volume=Quantity(row[self.dataset.columns.volume]),
            timestamp=close_timestamp,
            metadata=metadata,
        )

    @staticmethod
    def _dimension_value(
        row: Mapping[str, Any],
        column_name: str | None,
        default: str | None,
        label: str,
    ) -> str:
        if column_name is not None and column_name in row and row[column_name] is not None:
            return str(row[column_name])
        if default is not None:
            return default
        raise ValueError(f"missing required {label} value in parquet row")


@dataclass(frozen=True, slots=True)
class ParquetTradeDecoder:
    dataset: ResolvedParquetTradeDataset | ResolvedCsvTradeDataset
    _default_symbol_obj: Symbol | None = field(init=False, repr=False)
    _default_venue_obj: Venue | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_default_symbol_obj",
            None if self.dataset.default_symbol is None else Symbol(self.dataset.default_symbol),
        )
        object.__setattr__(
            self,
            "_default_venue_obj",
            None if self.dataset.default_venue is None else Venue(self.dataset.default_venue),
        )

    def required_columns(self) -> tuple[str, ...]:
        columns = [
            self.dataset.columns.timestamp,
            self.dataset.columns.price,
            self.dataset.columns.quantity,
        ]
        if self.dataset.columns.symbol is not None and self.dataset.default_symbol is None:
            columns.append(self.dataset.columns.symbol)
        if self.dataset.columns.venue is not None and self.dataset.default_venue is None:
            columns.append(self.dataset.columns.venue)
        return tuple(dict.fromkeys(columns))

    def decode_row(self, row: Mapping[str, Any]) -> TradeEvent:
        symbol = self._default_symbol_obj or Symbol(
            ParquetBarDecoder._dimension_value(row, self.dataset.columns.symbol, self.dataset.default_symbol, "symbol")
        )
        venue = self._default_venue_obj or Venue(
            ParquetBarDecoder._dimension_value(row, self.dataset.columns.venue, self.dataset.default_venue, "venue")
        )
        return TradeEvent(
            symbol=symbol,
            venue=venue,
            price=Price(row[self.dataset.columns.price]),
            quantity=Quantity(row[self.dataset.columns.quantity]),
            timestamp=_coerce_timestamp(row[self.dataset.columns.timestamp]),
        )


@dataclass(frozen=True, slots=True)
class ParquetTickDecoder:
    dataset: ResolvedParquetTickDataset | ResolvedCsvTickDataset
    _default_symbol_obj: Symbol | None = field(init=False, repr=False)
    _default_venue_obj: Venue | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_default_symbol_obj",
            None if self.dataset.default_symbol is None else Symbol(self.dataset.default_symbol),
        )
        object.__setattr__(
            self,
            "_default_venue_obj",
            None if self.dataset.default_venue is None else Venue(self.dataset.default_venue),
        )

    def required_columns(self) -> tuple[str, ...]:
        columns = [
            self.dataset.columns.timestamp,
            self.dataset.columns.bid,
            self.dataset.columns.ask,
        ]
        if self.dataset.columns.symbol is not None and self.dataset.default_symbol is None:
            columns.append(self.dataset.columns.symbol)
        if self.dataset.columns.venue is not None and self.dataset.default_venue is None:
            columns.append(self.dataset.columns.venue)
        return tuple(dict.fromkeys(columns))

    def decode_row(self, row: Mapping[str, Any]) -> TickEvent:
        symbol = self._default_symbol_obj or Symbol(
            ParquetBarDecoder._dimension_value(row, self.dataset.columns.symbol, self.dataset.default_symbol, "symbol")
        )
        venue = self._default_venue_obj or Venue(
            ParquetBarDecoder._dimension_value(row, self.dataset.columns.venue, self.dataset.default_venue, "venue")
        )
        return TickEvent(
            symbol=symbol,
            venue=venue,
            bid=Price(row[self.dataset.columns.bid]),
            ask=Price(row[self.dataset.columns.ask]),
            timestamp=_coerce_timestamp(row[self.dataset.columns.timestamp]),
        )

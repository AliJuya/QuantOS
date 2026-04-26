from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from qcore.domain.types import Price, Quantity, Symbol, Timeframe, Venue, ensure_utc


@dataclass(frozen=True, slots=True)
class TickEvent:
    symbol: Symbol
    venue: Venue
    bid: Price
    ask: Price
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class TradeEvent:
    symbol: Symbol
    venue: Venue
    price: Price
    quantity: Quantity
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class QuoteEvent:
    symbol: Symbol
    venue: Venue
    bid: Price
    ask: Price
    bid_size: Quantity
    ask_size: Quantity
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class BarOpenEvent:
    symbol: Symbol
    venue: Venue
    timeframe: Timeframe
    bar_open_time: datetime
    open_price: Price
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "bar_open_time", ensure_utc(self.bar_open_time))
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))


@dataclass(frozen=True, slots=True)
class BarCloseEvent:
    symbol: Symbol
    venue: Venue
    timeframe: Timeframe
    bar_open_time: datetime
    open_price: Price
    high_price: Price
    low_price: Price
    close_price: Price
    volume: Quantity
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bar_open_time", ensure_utc(self.bar_open_time))
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))

    @property
    def close_time(self) -> datetime:
        return self.timestamp

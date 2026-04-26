from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Symbol, Timeframe, Venue


@dataclass(frozen=True, slots=True)
class BarStreamKey:
    symbol: Symbol
    venue: Venue
    timeframe: Timeframe


@dataclass(slots=True)
class ClosedBarRiver:
    maxlen: int = 50_000
    _buffers: dict[BarStreamKey, Deque[BarCloseEvent]] = field(default_factory=dict)
    _pushes: int = 0
    _dropped: int = 0

    def __post_init__(self) -> None:
        if self.maxlen <= 0:
            raise ValueError("bar river maxlen must be positive")

    def append(self, event: BarCloseEvent) -> None:
        key = BarStreamKey(symbol=event.symbol, venue=event.venue, timeframe=event.timeframe)
        self.append_for_key(key, event)

    def append_for_key(self, key: BarStreamKey, event: BarCloseEvent) -> None:
        buffer = self._buffers.setdefault(key, deque())
        if len(buffer) >= self.maxlen:
            buffer.popleft()
            self._dropped += 1
        buffer.append(event)
        self._pushes += 1

    def prepend_many(self, key: BarStreamKey, events: tuple[BarCloseEvent, ...]) -> None:
        if not events:
            return
        buffer = self._buffers.setdefault(key, deque())
        for event in reversed(events):
            buffer.appendleft(event)
            if len(buffer) > self.maxlen:
                buffer.popleft()
                self._dropped += 1
            self._pushes += 1

    def last(self, key: BarStreamKey) -> BarCloseEvent | None:
        buffer = self._buffers.get(key)
        if not buffer:
            return None
        return buffer[-1]

    def window(self, key: BarStreamKey, size: int | None = None) -> tuple[BarCloseEvent, ...]:
        buffer = self._buffers.get(key)
        if not buffer:
            return ()
        if size is None or size <= 0:
            return tuple(buffer)
        return tuple(list(buffer)[-size:])

    def keys(self) -> tuple[BarStreamKey, ...]:
        return tuple(self._buffers.keys())

    def stats(self) -> dict[str, int]:
        return {
            "streams": len(self._buffers),
            "pushes": self._pushes,
            "dropped": self._dropped,
        }

from __future__ import annotations

from dataclasses import dataclass, field

from qcore.data.streams import BarStreamKey, ClosedBarRiver
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Symbol, Timeframe, Venue


@dataclass(slots=True)
class MarketStore:
    bar_river: ClosedBarRiver = field(default_factory=ClosedBarRiver)
    latest_by_symbol: dict[Symbol, BarCloseEvent] = field(default_factory=dict)
    latest_by_stream: dict[BarStreamKey, BarCloseEvent] = field(default_factory=dict)

    def on_bar_close(self, event: BarCloseEvent) -> None:
        self.store_bar(event)
        return None

    def store_bar(self, event: BarCloseEvent) -> None:
        stream_key = BarStreamKey(symbol=event.symbol, venue=event.venue, timeframe=event.timeframe)
        self.bar_river.append_for_key(stream_key, event)
        self._update_latest(stream_key, event)

    def seed_bars(self, events: tuple[BarCloseEvent, ...], *, prepend: bool = False) -> None:
        if not events:
            return
        grouped: dict[BarStreamKey, list[BarCloseEvent]] = {}
        for event in events:
            key = BarStreamKey(symbol=event.symbol, venue=event.venue, timeframe=event.timeframe)
            grouped.setdefault(key, []).append(event)

        for key, group in grouped.items():
            ordered = tuple(sorted(group, key=lambda event: event.timestamp))
            if prepend:
                self.bar_river.prepend_many(key, ordered)
            else:
                for event in ordered:
                    self.bar_river.append_for_key(key, event)
                    self._update_latest(key, event)

    def _update_latest(self, stream_key: BarStreamKey, event: BarCloseEvent) -> None:
        current_symbol = self.latest_by_symbol.get(event.symbol)
        if current_symbol is None or event.timestamp >= current_symbol.timestamp:
            self.latest_by_symbol[event.symbol] = event

        current_stream = self.latest_by_stream.get(stream_key)
        if current_stream is None or event.timestamp >= current_stream.timestamp:
            self.latest_by_stream[stream_key] = event

    def price_for(
        self,
        symbol: Symbol,
        *,
        timeframe: Timeframe | None = None,
        venue: Venue | None = None,
    ) -> Price | None:
        if timeframe is not None and venue is not None:
            bar = self.latest_by_stream.get(BarStreamKey(symbol=symbol, venue=venue, timeframe=timeframe))
        else:
            bar = self.latest_by_symbol.get(symbol)
        if bar is None:
            return None
        return bar.close_price

    def last_bar(
        self,
        symbol: Symbol,
        *,
        timeframe: Timeframe | None = None,
        venue: Venue | None = None,
    ) -> BarCloseEvent | None:
        if timeframe is not None and venue is not None:
            return self.latest_by_stream.get(BarStreamKey(symbol=symbol, venue=venue, timeframe=timeframe))
        return self.latest_by_symbol.get(symbol)

    def window(
        self,
        *,
        symbol: Symbol,
        venue: Venue,
        timeframe: Timeframe,
        size: int | None = None,
    ) -> tuple[BarCloseEvent, ...]:
        return self.bar_river.window(
            BarStreamKey(symbol=symbol, venue=venue, timeframe=timeframe),
            size=size,
        )

    def streams(self) -> tuple[BarStreamKey, ...]:
        return self.bar_river.keys()

    def stats(self) -> dict[str, int]:
        stats = self.bar_river.stats()
        stats["latest_symbols"] = len(self.latest_by_symbol)
        stats["latest_streams"] = len(self.latest_by_stream)
        return stats

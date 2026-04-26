from __future__ import annotations

from dataclasses import dataclass

from qcore.data.calendars import SessionContext, TradingCalendarProtocol
from qcore.data.stores import MarketStore
from qcore.data.streams import BarStreamKey
from qcore.domain.events import BarCloseEvent
from qcore.domain.types import Price, Symbol, Timeframe, Venue


@dataclass(frozen=True, slots=True)
class MarketDataView:
    """
    Read-only market view for strategies, models, and risk policies.

    This keeps market reads explicit while preserving a single owning writer in the store.
    """

    store: MarketStore
    calendar: TradingCalendarProtocol

    def price_for(
        self,
        symbol: Symbol,
        *,
        timeframe: Timeframe | None = None,
        venue: Venue | None = None,
    ) -> Price | None:
        return self.store.price_for(symbol, timeframe=timeframe, venue=venue)

    def last_bar(
        self,
        symbol: Symbol,
        *,
        timeframe: Timeframe | None = None,
        venue: Venue | None = None,
    ) -> BarCloseEvent | None:
        return self.store.last_bar(symbol, timeframe=timeframe, venue=venue)

    def window(
        self,
        *,
        symbol: Symbol,
        venue: Venue,
        timeframe: Timeframe,
        size: int | None = None,
    ) -> tuple[BarCloseEvent, ...]:
        return self.store.window(symbol=symbol, venue=venue, timeframe=timeframe, size=size)

    def streams(self) -> tuple[BarStreamKey, ...]:
        return self.store.streams()

    def stats(self) -> dict[str, int]:
        return self.store.stats()

    def session_context(self, timestamp) -> SessionContext:
        return self.calendar.session_context(timestamp)

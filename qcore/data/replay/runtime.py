from __future__ import annotations

from dataclasses import dataclass

from qcore.data.engine import MarketDataEngine
from qcore.domain.contracts import EventBusProtocol
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent


@dataclass(frozen=True, slots=True)
class ReplayIngestionRuntime:
    data_engine: MarketDataEngine

    def register(self, bus: EventBusProtocol) -> None:
        bus.subscribe(TickEvent, self.data_engine.on_tick)
        bus.subscribe(TradeEvent, self.data_engine.on_trade)
        bus.subscribe(BarCloseEvent, self.data_engine.on_bar_close)

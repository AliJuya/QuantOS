from __future__ import annotations

from dataclasses import dataclass

from qcore.data.engine import MarketDataEngine
from qcore.data.replay.runtime import ReplayIngestionRuntime
from qcore.domain.contracts import EventBusProtocol, LiveMarketDataSourceProtocol


@dataclass(slots=True)
class LiveIngestionRuntime:
    data_engine: MarketDataEngine
    source: LiveMarketDataSourceProtocol
    event_bus: EventBusProtocol
    _started: bool = False

    def start(self) -> None:
        if self._started:
            return
        ReplayIngestionRuntime(self.data_engine).register(self.event_bus)
        self.source.start(self.event_bus)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self.source.stop()
        self._started = False

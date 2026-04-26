from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from qcore.domain.contracts import EventBusProtocol
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent
from qcore.domain.types import Price, Quantity, SourceDescriptor, Symbol, Timeframe, Venue


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decode_scripted_event(payload: dict[str, object]) -> object:
    event_type = str(payload["event_type"]).strip().lower()
    symbol = Symbol(str(payload["symbol"]))
    venue = Venue(str(payload["venue"]))
    timestamp = _parse_timestamp(str(payload["timestamp"]))

    if event_type == "trade":
        return TradeEvent(
            symbol=symbol,
            venue=venue,
            price=Price(str(payload["price"])),
            quantity=Quantity(str(payload["quantity"])),
            timestamp=timestamp,
        )
    if event_type == "tick":
        return TickEvent(
            symbol=symbol,
            venue=venue,
            bid=Price(str(payload["bid"])),
            ask=Price(str(payload["ask"])),
            timestamp=timestamp,
        )
    if event_type == "bar_close":
        return BarCloseEvent(
            symbol=symbol,
            venue=venue,
            timeframe=Timeframe(str(payload["timeframe"])),
            bar_open_time=_parse_timestamp(str(payload["bar_open_time"])),
            open_price=Price(str(payload["open_price"])),
            high_price=Price(str(payload["high_price"])),
            low_price=Price(str(payload["low_price"])),
            close_price=Price(str(payload["close_price"])),
            volume=Quantity(str(payload["volume"])),
            timestamp=timestamp,
        )
    raise ValueError(f"unsupported scripted event type: {event_type}")


@dataclass(slots=True)
class JsonlScriptedLiveMarketDataSource:
    script_path: Path
    input_mode: str
    source_timeframe: str | None = None
    source_id: str = "simulator_scripted_live"
    emit_delay_seconds: float = 0.0
    _running: bool = field(default=False, init=False)

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_id=self.source_id,
            source_type="simulator",
            mode="live",
            ordering="script_order",
            locations=(self.script_path.resolve(),),
            source_timeframe=self.source_timeframe,
            metadata={
                "input_mode": self.input_mode,
                "emit_delay_seconds": self.emit_delay_seconds,
            },
        )

    def start(self, event_bus: EventBusProtocol) -> None:
        self._running = True
        for event in self.iter_events():
            if not self._running:
                break
            event_bus.publish(event)
            if self.emit_delay_seconds > 0:
                time.sleep(self.emit_delay_seconds)
        self._running = False

    def stop(self) -> None:
        self._running = False

    def iter_events(self) -> Iterator[object]:
        with self.script_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield _decode_scripted_event(json.loads(line))

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from qcore.domain.contracts import EventBusProtocol
from qcore.domain.events import BarCloseEvent, TickEvent, TradeEvent
from qcore.domain.types import Price, Quantity, SourceDescriptor, Symbol, Timeframe, Venue


def _ensure_utc_datetime_from_ms(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)


@dataclass(slots=True)
class BinanceWebSocketMarketDataSource:
    symbol: str
    input_mode: str
    source_timeframe: str | None = None
    venue: str = "BINANCE"
    endpoint_base: str = "wss://stream.binance.com:9443/ws"
    _running: bool = field(default=False, init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _websocket: Any | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.input_mode = str(self.input_mode).strip().lower()
        if self.input_mode not in {"bars", "trades", "ticks"}:
            raise ValueError("input_mode must be one of: bars, trades, ticks")
        if self.input_mode == "bars" and self.source_timeframe is None:
            raise ValueError("source_timeframe is required for binance bar streams")

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_id="binance_websocket",
            source_type="websocket",
            mode="live",
            ordering="event_time",
            source_timeframe=self.source_timeframe,
            metadata={
                "symbol": self.symbol.upper(),
                "input_mode": self.input_mode,
                "stream": self._stream_name(),
                "endpoint_base": self.endpoint_base,
            },
        )

    def start(self, event_bus: EventBusProtocol) -> None:
        self._running = True
        asyncio.run(self._consume(event_bus))

    def stop(self) -> None:
        self._running = False
        if self._loop is not None and self._websocket is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._websocket.close(), self._loop)
            except RuntimeError:
                pass

    async def _consume(self, event_bus: EventBusProtocol) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Binance live source requires the 'websockets' package") from exc

        self._loop = asyncio.get_running_loop()
        uri = f"{self.endpoint_base}/{self._stream_name()}"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
            self._websocket = websocket
            while self._running:
                raw = await websocket.recv()
                event = self.decode_message(json.loads(raw))
                if event is not None:
                    event_bus.publish(event)
        self._websocket = None

    def decode_message(self, payload: dict[str, Any]) -> object | None:
        if self.input_mode == "trades":
            return self._decode_trade(payload)
        if self.input_mode == "ticks":
            return self._decode_tick(payload)
        return self._decode_bar_close(payload)

    def _decode_trade(self, payload: dict[str, Any]) -> TradeEvent:
        symbol = Symbol(str(payload["s"]))
        venue = Venue(self.venue)
        return TradeEvent(
            symbol=symbol,
            venue=venue,
            price=Price(str(payload["p"])),
            quantity=Quantity(str(payload["q"])),
            timestamp=_ensure_utc_datetime_from_ms(payload["T"]),
        )

    def _decode_tick(self, payload: dict[str, Any]) -> TickEvent:
        symbol = Symbol(str(payload["s"]))
        venue = Venue(self.venue)
        event_time = payload.get("E") or payload.get("T") or int(datetime.now(tz=UTC).timestamp() * 1000)
        return TickEvent(
            symbol=symbol,
            venue=venue,
            bid=Price(str(payload["b"])),
            ask=Price(str(payload["a"])),
            timestamp=_ensure_utc_datetime_from_ms(event_time),
        )

    def _decode_bar_close(self, payload: dict[str, Any]) -> BarCloseEvent | None:
        kline = payload["k"]
        if not bool(kline["x"]):
            return None
        timeframe = Timeframe(str(kline["i"]))
        return BarCloseEvent(
            symbol=Symbol(str(payload["s"])),
            venue=Venue(self.venue),
            timeframe=timeframe,
            bar_open_time=_ensure_utc_datetime_from_ms(kline["t"]),
            open_price=Price(str(kline["o"])),
            high_price=Price(str(kline["h"])),
            low_price=Price(str(kline["l"])),
            close_price=Price(str(kline["c"])),
            volume=Quantity(str(kline["v"])),
            timestamp=_ensure_utc_datetime_from_ms(kline["T"]),
        )

    def _stream_name(self) -> str:
        symbol = self.symbol.lower()
        if self.input_mode == "trades":
            return f"{symbol}@trade"
        if self.input_mode == "ticks":
            return f"{symbol}@bookTicker"
        timeframe = str(self.source_timeframe).lower()
        return f"{symbol}@kline_{timeframe}"

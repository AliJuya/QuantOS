from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.exchanges.binance import BinanceWebSocketMarketDataSource
from adapters.exchanges.simulator import JsonlScriptedLiveMarketDataSource
from qcore.domain.contracts import LiveMarketDataSourceProtocol
from qcore.domain.types import Timeframe


@dataclass(frozen=True, slots=True)
class LiveSourceBuildResult:
    source: LiveMarketDataSourceProtocol
    source_timeframe: Timeframe
    input_mode: str


class LiveSourceFactory:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(self, data_config: dict[str, Any]) -> LiveSourceBuildResult:
        adapter = str(data_config.get("adapter", "")).strip().lower()
        input_mode = str(data_config.get("input_mode", "bars")).strip().lower()
        source_timeframe = self._source_timeframe(data_config)

        if adapter == "simulator":
            path = self._resolve_path(str(data_config["path"]))
            source = JsonlScriptedLiveMarketDataSource(
                script_path=path,
                input_mode=input_mode,
                source_timeframe=str(source_timeframe),
                emit_delay_seconds=float(data_config.get("emit_delay_seconds", 0.0)),
            )
            return LiveSourceBuildResult(source=source, source_timeframe=source_timeframe, input_mode=input_mode)

        if adapter == "binance":
            symbol = str(data_config["symbol"])
            source = BinanceWebSocketMarketDataSource(
                symbol=symbol,
                input_mode=input_mode,
                source_timeframe=str(source_timeframe) if input_mode == "bars" else None,
                venue=str(data_config.get("venue", "BINANCE")),
                endpoint_base=str(data_config.get("endpoint_base", "wss://stream.binance.com:9443/ws")),
            )
            return LiveSourceBuildResult(source=source, source_timeframe=source_timeframe, input_mode=input_mode)

        raise ValueError(f"unsupported live data adapter: {adapter}")

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    @staticmethod
    def _source_timeframe(data_config: dict[str, Any]) -> Timeframe:
        configured = data_config.get("source_timeframe")
        if configured is None:
            raise ValueError("data.source_timeframe is required for live sources")
        return Timeframe(str(configured))

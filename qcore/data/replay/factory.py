from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qcore.data.catalog import (
    CsvBarColumnMapping,
    CsvBarDatasetSpec,
    CsvTickColumnMapping,
    CsvTickDatasetSpec,
    CsvTradeColumnMapping,
    CsvTradeDatasetSpec,
    LocalCsvCatalog,
    LocalParquetCatalog,
    ParquetBarColumnMapping,
    ParquetBarDatasetSpec,
    ParquetTickColumnMapping,
    ParquetTickDatasetSpec,
    ParquetTradeColumnMapping,
    ParquetTradeDatasetSpec,
)
from qcore.data.replay.csv_bars import CsvBarReplaySource
from qcore.data.replay.csv_ticks import CsvTickReplaySource
from qcore.data.replay.csv_trades import CsvTradeReplaySource
from qcore.data.replay.parquet_bars import ParquetBarReplaySource
from qcore.data.replay.parquet_ticks import ParquetTickReplaySource
from qcore.data.replay.parquet_trades import ParquetTradeReplaySource
from qcore.domain.contracts import MarketDataSourceProtocol
from qcore.domain.types import Timeframe


@dataclass(frozen=True, slots=True)
class ReplaySourceBuildResult:
    source: MarketDataSourceProtocol
    source_timeframe: Timeframe
    input_mode: str
    resolved_data_files: tuple[Path, ...]
    source_locations: tuple[Path, ...]


class ReplaySourceFactory:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(self, data_config: dict[str, Any]) -> ReplaySourceBuildResult:
        adapter = str(data_config.get("adapter", "parquet")).strip().lower()
        input_mode = str(data_config.get("input_mode", "bars")).strip().lower()
        locations = self._resolve_locations(data_config)
        batch_size = int(data_config.get("batch_size", 4096))

        if adapter == "parquet":
            return self._build_parquet_source(
                data_config=data_config,
                input_mode=input_mode,
                locations=locations,
                batch_size=batch_size,
            )

        if adapter == "csv":
            return self._build_csv_source(
                data_config=data_config,
                input_mode=input_mode,
                locations=locations,
                batch_size=batch_size,
            )

        raise ValueError(f"unsupported data adapter: {adapter}")

    def _build_parquet_source(
        self,
        *,
        data_config: dict[str, Any],
        input_mode: str,
        locations: tuple[Path, ...],
        batch_size: int,
    ) -> ReplaySourceBuildResult:
        catalog = LocalParquetCatalog()
        if input_mode == "bars":
            dataset = catalog.resolve_bars(
                ParquetBarDatasetSpec(
                    locations=locations,
                    columns=ParquetBarColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    default_timeframe=data_config.get("default_timeframe"),
                    timestamp_is=data_config.get("timestamp_is", "close"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=ParquetBarReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, dataset.default_timeframe),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        if input_mode == "trades":
            dataset = catalog.resolve_trades(
                ParquetTradeDatasetSpec(
                    locations=locations,
                    columns=ParquetTradeColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=ParquetTradeReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, None),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        if input_mode == "ticks":
            dataset = catalog.resolve_ticks(
                ParquetTickDatasetSpec(
                    locations=locations,
                    columns=ParquetTickColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=ParquetTickReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, None),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        raise ValueError(f"unsupported data.input_mode: {input_mode}")

    def _build_csv_source(
        self,
        *,
        data_config: dict[str, Any],
        input_mode: str,
        locations: tuple[Path, ...],
        batch_size: int,
    ) -> ReplaySourceBuildResult:
        catalog = LocalCsvCatalog()
        if input_mode == "bars":
            dataset = catalog.resolve_bars(
                CsvBarDatasetSpec(
                    locations=locations,
                    columns=CsvBarColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    default_timeframe=data_config.get("default_timeframe"),
                    timestamp_is=data_config.get("timestamp_is", "close"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=CsvBarReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, dataset.default_timeframe),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        if input_mode == "trades":
            dataset = catalog.resolve_trades(
                CsvTradeDatasetSpec(
                    locations=locations,
                    columns=CsvTradeColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=CsvTradeReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, None),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        if input_mode == "ticks":
            dataset = catalog.resolve_ticks(
                CsvTickDatasetSpec(
                    locations=locations,
                    columns=CsvTickColumnMapping(**data_config.get("columns", {})),
                    default_symbol=data_config.get("default_symbol"),
                    default_venue=data_config.get("default_venue"),
                    batch_size=batch_size,
                )
            )
            return ReplaySourceBuildResult(
                source=CsvTickReplaySource(dataset),
                source_timeframe=self._source_timeframe(data_config, None),
                input_mode=input_mode,
                resolved_data_files=dataset.paths,
                source_locations=dataset.source_locations,
            )

        raise ValueError(f"unsupported data.input_mode: {input_mode}")

    def _resolve_locations(self, data_config: dict[str, Any]) -> tuple[Path, ...]:
        raw_locations = data_config.get("paths")
        if raw_locations is None:
            raw_path = data_config.get("path")
            if raw_path is None:
                raise ValueError("data config requires 'paths' or 'path'")
            raw_locations = [raw_path]
        return tuple(self._resolve_path(str(location)) for location in raw_locations)

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    @staticmethod
    def _source_timeframe(data_config: dict[str, Any], dataset_default_timeframe: str | None) -> Timeframe:
        configured = data_config.get("source_timeframe") or dataset_default_timeframe
        if configured is None:
            raise ValueError("data.source_timeframe or dataset default_timeframe is required")
        return Timeframe(str(configured))

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _validate_locations_and_batch_size(locations: tuple[Path, ...], batch_size: int) -> None:
    if not locations:
        raise ValueError("parquet dataset spec requires at least one location")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _resolve_parquet_paths(locations: tuple[Path, ...]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for location in locations:
        if location.is_file():
            if location.suffix.lower() != ".parquet":
                raise ValueError(f"expected parquet file: {location}")
            paths.append(location.resolve())
            continue
        if location.is_dir():
            paths.extend(sorted(path.resolve() for path in location.rglob("*.parquet")))
            continue
        raise FileNotFoundError(f"dataset location does not exist: {location}")

    deduplicated = tuple(dict.fromkeys(paths))
    if not deduplicated:
        raise FileNotFoundError(
            "no parquet files found under dataset locations: "
            + ", ".join(str(path) for path in locations)
        )
    return deduplicated


@dataclass(frozen=True, slots=True)
class ParquetBarColumnMapping:
    timestamp: str = "timestamp"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"
    quote_volume: str | None = None
    taker_buy_quote_volume: str | None = None
    taker_buy_base_volume: str | None = None
    symbol: str | None = "symbol"
    venue: str | None = "venue"
    timeframe: str | None = "timeframe"


@dataclass(frozen=True, slots=True)
class ParquetBarDatasetSpec:
    locations: tuple[Path, ...]
    columns: ParquetBarColumnMapping = field(default_factory=ParquetBarColumnMapping)
    default_symbol: str | None = None
    default_venue: str | None = None
    default_timeframe: str | None = None
    timestamp_is: str = "close"
    batch_size: int = 4096

    def __post_init__(self) -> None:
        _validate_locations_and_batch_size(self.locations, self.batch_size)
        if self.timestamp_is not in {"open", "close"}:
            raise ValueError("timestamp_is must be 'open' or 'close'")


@dataclass(frozen=True, slots=True)
class ResolvedParquetBarDataset:
    paths: tuple[Path, ...]
    columns: ParquetBarColumnMapping
    default_symbol: str | None
    default_venue: str | None
    default_timeframe: str | None
    timestamp_is: str
    batch_size: int
    source_locations: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ParquetTradeColumnMapping:
    timestamp: str = "timestamp"
    price: str = "price"
    quantity: str = "quantity"
    symbol: str | None = "symbol"
    venue: str | None = "venue"


@dataclass(frozen=True, slots=True)
class ParquetTradeDatasetSpec:
    locations: tuple[Path, ...]
    columns: ParquetTradeColumnMapping = field(default_factory=ParquetTradeColumnMapping)
    default_symbol: str | None = None
    default_venue: str | None = None
    batch_size: int = 4096

    def __post_init__(self) -> None:
        _validate_locations_and_batch_size(self.locations, self.batch_size)


@dataclass(frozen=True, slots=True)
class ResolvedParquetTradeDataset:
    paths: tuple[Path, ...]
    columns: ParquetTradeColumnMapping
    default_symbol: str | None
    default_venue: str | None
    batch_size: int
    source_locations: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ParquetTickColumnMapping:
    timestamp: str = "timestamp"
    bid: str = "bid"
    ask: str = "ask"
    symbol: str | None = "symbol"
    venue: str | None = "venue"


@dataclass(frozen=True, slots=True)
class ParquetTickDatasetSpec:
    locations: tuple[Path, ...]
    columns: ParquetTickColumnMapping = field(default_factory=ParquetTickColumnMapping)
    default_symbol: str | None = None
    default_venue: str | None = None
    batch_size: int = 4096

    def __post_init__(self) -> None:
        _validate_locations_and_batch_size(self.locations, self.batch_size)


@dataclass(frozen=True, slots=True)
class ResolvedParquetTickDataset:
    paths: tuple[Path, ...]
    columns: ParquetTickColumnMapping
    default_symbol: str | None
    default_venue: str | None
    batch_size: int
    source_locations: tuple[Path, ...]


class LocalParquetCatalog:
    def resolve(self, spec: ParquetBarDatasetSpec) -> ResolvedParquetBarDataset:
        return self.resolve_bars(spec)

    def resolve_bars(self, spec: ParquetBarDatasetSpec) -> ResolvedParquetBarDataset:
        deduplicated = _resolve_parquet_paths(spec.locations)
        return ResolvedParquetBarDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            default_timeframe=spec.default_timeframe,
            timestamp_is=spec.timestamp_is,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

    def resolve_trades(self, spec: ParquetTradeDatasetSpec) -> ResolvedParquetTradeDataset:
        deduplicated = _resolve_parquet_paths(spec.locations)
        return ResolvedParquetTradeDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

    def resolve_ticks(self, spec: ParquetTickDatasetSpec) -> ResolvedParquetTickDataset:
        deduplicated = _resolve_parquet_paths(spec.locations)
        return ResolvedParquetTickDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

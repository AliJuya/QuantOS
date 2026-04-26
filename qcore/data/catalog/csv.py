from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _validate_locations_and_batch_size(locations: tuple[Path, ...], batch_size: int) -> None:
    if not locations:
        raise ValueError("csv dataset spec requires at least one location")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _resolve_csv_paths(locations: tuple[Path, ...]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for location in locations:
        if location.is_file():
            if location.suffix.lower() != ".csv":
                raise ValueError(f"expected csv file: {location}")
            paths.append(location.resolve())
            continue
        if location.is_dir():
            paths.extend(sorted(path.resolve() for path in location.rglob("*.csv")))
            continue
        raise FileNotFoundError(f"dataset location does not exist: {location}")

    deduplicated = tuple(dict.fromkeys(paths))
    if not deduplicated:
        raise FileNotFoundError(
            "no csv files found under dataset locations: "
            + ", ".join(str(path) for path in locations)
        )
    return deduplicated


@dataclass(frozen=True, slots=True)
class CsvBarColumnMapping:
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
class CsvBarDatasetSpec:
    locations: tuple[Path, ...]
    columns: CsvBarColumnMapping = field(default_factory=CsvBarColumnMapping)
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
class ResolvedCsvBarDataset:
    paths: tuple[Path, ...]
    columns: CsvBarColumnMapping
    default_symbol: str | None
    default_venue: str | None
    default_timeframe: str | None
    timestamp_is: str
    batch_size: int
    source_locations: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class CsvTradeColumnMapping:
    timestamp: str = "timestamp"
    price: str = "price"
    quantity: str = "quantity"
    symbol: str | None = "symbol"
    venue: str | None = "venue"


@dataclass(frozen=True, slots=True)
class CsvTradeDatasetSpec:
    locations: tuple[Path, ...]
    columns: CsvTradeColumnMapping = field(default_factory=CsvTradeColumnMapping)
    default_symbol: str | None = None
    default_venue: str | None = None
    batch_size: int = 4096

    def __post_init__(self) -> None:
        _validate_locations_and_batch_size(self.locations, self.batch_size)


@dataclass(frozen=True, slots=True)
class ResolvedCsvTradeDataset:
    paths: tuple[Path, ...]
    columns: CsvTradeColumnMapping
    default_symbol: str | None
    default_venue: str | None
    batch_size: int
    source_locations: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class CsvTickColumnMapping:
    timestamp: str = "timestamp"
    bid: str = "bid"
    ask: str = "ask"
    symbol: str | None = "symbol"
    venue: str | None = "venue"


@dataclass(frozen=True, slots=True)
class CsvTickDatasetSpec:
    locations: tuple[Path, ...]
    columns: CsvTickColumnMapping = field(default_factory=CsvTickColumnMapping)
    default_symbol: str | None = None
    default_venue: str | None = None
    batch_size: int = 4096

    def __post_init__(self) -> None:
        _validate_locations_and_batch_size(self.locations, self.batch_size)


@dataclass(frozen=True, slots=True)
class ResolvedCsvTickDataset:
    paths: tuple[Path, ...]
    columns: CsvTickColumnMapping
    default_symbol: str | None
    default_venue: str | None
    batch_size: int
    source_locations: tuple[Path, ...]


class LocalCsvCatalog:
    def resolve_bars(self, spec: CsvBarDatasetSpec) -> ResolvedCsvBarDataset:
        deduplicated = _resolve_csv_paths(spec.locations)
        return ResolvedCsvBarDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            default_timeframe=spec.default_timeframe,
            timestamp_is=spec.timestamp_is,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

    def resolve_trades(self, spec: CsvTradeDatasetSpec) -> ResolvedCsvTradeDataset:
        deduplicated = _resolve_csv_paths(spec.locations)
        return ResolvedCsvTradeDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

    def resolve_ticks(self, spec: CsvTickDatasetSpec) -> ResolvedCsvTickDataset:
        deduplicated = _resolve_csv_paths(spec.locations)
        return ResolvedCsvTickDataset(
            paths=deduplicated,
            columns=spec.columns,
            default_symbol=spec.default_symbol,
            default_venue=spec.default_venue,
            batch_size=spec.batch_size,
            source_locations=tuple(path.resolve() for path in spec.locations),
        )

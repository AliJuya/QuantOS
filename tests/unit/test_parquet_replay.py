from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from qcore.data.catalog import (
    LocalParquetCatalog,
    ParquetBarDatasetSpec,
    ParquetTickDatasetSpec,
    ParquetTradeDatasetSpec,
)
from qcore.data.replay import ParquetBarReplaySource, ParquetTickReplaySource, ParquetTradeReplaySource


def test_parquet_replay_source_decodes_ordered_bar_events() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dataset = LocalParquetCatalog().resolve(
        ParquetBarDatasetSpec(
            locations=(project_root / "tests/fixtures/data/ema_cross_sample_bars.parquet",),
        )
    )
    source = ParquetBarReplaySource(dataset)

    events = list(source.iter_events())

    assert len(events) == 15
    assert events[0].symbol.value == "BTCUSDT"
    assert events[0].bar_open_time == datetime(2025, 12, 31, tzinfo=UTC)
    assert events[-1].timestamp == datetime(2026, 1, 15, tzinfo=UTC)


def test_parquet_trade_replay_source_decodes_ordered_trade_events(tmp_path: Path) -> None:
    path = tmp_path / "trades.parquet"
    table = pa.table(
        {
            "timestamp": [
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
                datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
            ],
            "price": [100.0, 101.5],
            "quantity": [1.25, 0.5],
        }
    )
    pq.write_table(table, path)

    dataset = LocalParquetCatalog().resolve_trades(
        ParquetTradeDatasetSpec(
            locations=(path,),
            default_symbol="ETHUSDT",
            default_venue="SIM",
        )
    )
    events = list(ParquetTradeReplaySource(dataset).iter_events())

    assert len(events) == 2
    assert events[0].symbol.value == "ETHUSDT"
    assert events[0].price.value == 100
    assert events[1].quantity.value == 0.5


def test_parquet_tick_replay_source_decodes_ordered_tick_events(tmp_path: Path) -> None:
    path = tmp_path / "ticks.parquet"
    table = pa.table(
        {
            "timestamp": [
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
                datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
            ],
            "bid": [99.5, 100.0],
            "ask": [100.5, 101.0],
        }
    )
    pq.write_table(table, path)

    dataset = LocalParquetCatalog().resolve_ticks(
        ParquetTickDatasetSpec(
            locations=(path,),
            default_symbol="ETHUSDT",
            default_venue="SIM",
        )
    )
    events = list(ParquetTickReplaySource(dataset).iter_events())

    assert len(events) == 2
    assert events[0].symbol.value == "ETHUSDT"
    assert events[0].bid.value == 99.5
    assert events[1].ask.value == 101

from pathlib import Path

from qcore.data.catalog import LocalParquetCatalog, ParquetBarDatasetSpec
from qcore.data.replay import ParquetBarReplaySource


def test_parquet_replay_source_exposes_descriptor() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dataset = LocalParquetCatalog().resolve(
        ParquetBarDatasetSpec(
            locations=(project_root / "tests/fixtures/data/ema_cross_sample_bars.parquet",),
        )
    )

    descriptor = ParquetBarReplaySource(dataset).descriptor()

    assert descriptor.source_type == "parquet"
    assert descriptor.mode == "replay"
    assert descriptor.ordering == "monotonic_bar_close_time"
    assert descriptor.metadata["input_mode"] == "bars"
    assert len(descriptor.locations) == 1

from pathlib import Path

from qcore.data.replay import ReplaySourceFactory


def test_replay_source_factory_builds_csv_trade_source(tmp_path: Path) -> None:
    path = tmp_path / "trades.csv"
    path.write_text(
        "timestamp,price,quantity,symbol,venue\n"
        "2026-01-01T00:00:01Z,100,1,ETHUSDT,SIM\n",
        encoding="utf-8",
    )

    bundle = ReplaySourceFactory(tmp_path).build(
        {
            "adapter": "csv",
            "input_mode": "trades",
            "source_timeframe": "1m",
            "path": str(path),
        }
    )

    assert bundle.input_mode == "trades"
    assert bundle.source.descriptor().source_type == "csv"
    assert bundle.source_timeframe.value == "1m"
    assert len(bundle.resolved_data_files) == 1

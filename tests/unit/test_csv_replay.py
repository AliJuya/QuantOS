from datetime import UTC, datetime
from pathlib import Path

from qcore.data.catalog import (
    CsvBarDatasetSpec,
    CsvTickDatasetSpec,
    CsvTradeDatasetSpec,
    LocalCsvCatalog,
)
from qcore.data.replay import CsvBarReplaySource, CsvTickReplaySource, CsvTradeReplaySource


def test_csv_bar_replay_source_decodes_ordered_bar_events(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume,symbol,venue,timeframe\n"
        "2026-01-01T00:01:00Z,100,101,99,100.5,12,BTCUSDT,SIM,1m\n"
        "2026-01-01T00:02:00Z,100.5,102,100,101.5,10,BTCUSDT,SIM,1m\n",
        encoding="utf-8",
    )
    dataset = LocalCsvCatalog().resolve_bars(CsvBarDatasetSpec(locations=(path,)))

    events = list(CsvBarReplaySource(dataset).iter_events())

    assert len(events) == 2
    assert events[0].bar_open_time == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert events[1].close_price.value == 101.5


def test_csv_trade_replay_source_decodes_ordered_trade_events(tmp_path: Path) -> None:
    path = tmp_path / "trades.csv"
    path.write_text(
        "timestamp,price,quantity,symbol,venue\n"
        "2026-01-01T00:00:01Z,100,1.25,ETHUSDT,SIM\n"
        "2026-01-01T00:00:02Z,101.5,0.5,ETHUSDT,SIM\n",
        encoding="utf-8",
    )
    dataset = LocalCsvCatalog().resolve_trades(CsvTradeDatasetSpec(locations=(path,)))

    events = list(CsvTradeReplaySource(dataset).iter_events())

    assert len(events) == 2
    assert events[0].symbol.value == "ETHUSDT"
    assert events[1].quantity.value == 0.5


def test_csv_tick_replay_source_decodes_ordered_tick_events(tmp_path: Path) -> None:
    path = tmp_path / "ticks.csv"
    path.write_text(
        "timestamp,bid,ask,symbol,venue\n"
        "2026-01-01T00:00:01Z,99.5,100.5,ETHUSDT,SIM\n"
        "2026-01-01T00:00:02Z,100,101,ETHUSDT,SIM\n",
        encoding="utf-8",
    )
    dataset = LocalCsvCatalog().resolve_ticks(CsvTickDatasetSpec(locations=(path,)))

    events = list(CsvTickReplaySource(dataset).iter_events())

    assert len(events) == 2
    assert events[0].bid.value == 99.5
    assert events[1].ask.value == 101

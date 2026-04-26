from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from qcore.analytics.reporter import (
    _build_equity_curve,
    _compute_metrics,
    _compute_period_rows,
    _load_equity_rows,
    _load_trade_events,
    _parse_year_month,
    generate_backtest_report,
)
from qcore.data.calendars import WindowedSessionCalendar


def _write_manifest(run_dir: Path) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": {"value": "test-run"},
            "app_name": "backtester",
            "mode": "backtest",
            "metadata": {
                "calendar_config": {
                    "kind": "windowed",
                    "calendar_id": "sessions",
                    "timezone": "UTC",
                    "out_of_session_label": "closed",
                    "windows": [
                        {"label": "europe", "start_hour": 8, "end_hour": 16},
                        {"label": "us", "start_hour": 16, "end_hour": 23},
                    ],
                },
            },
        }),
        encoding="utf-8",
    )


def _write_equity(run_dir: Path, rows: list[tuple[str, float]]) -> None:
    path = run_dir / "equity.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for timestamp, equity in rows:
            handle.write(json.dumps({
                "timestamp": timestamp,
                "balance": {
                    "equity": {"amount": str(equity), "currency": "USD"},
                    "cash": {"amount": str(equity - 100), "currency": "USD"},
                    "fees_paid": {"amount": "5", "currency": "USD"},
                    "timestamp": timestamp,
                },
                "positions": [],
                "realized_pnl": {"amount": "0", "currency": "USD"},
                "unrealized_pnl": {"amount": "0", "currency": "USD"},
                "net_pnl": {"amount": "0", "currency": "USD"},
            }) + "\n")


def _write_trades(run_dir: Path) -> None:
    path = run_dir / "trades.jsonl"
    rows = [
        {
            "trade_id": {"value": "trade-1"},
            "strategy_id": {"value": "ema_fast"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "LONG",
            "quantity": {"value": "1"},
            "entry_price": {"value": "100"},
            "exit_price": {"value": "105"},
            "entry_timestamp": "2022-01-03T09:00:00+00:00",
            "exit_timestamp": "2022-01-03T10:00:00+00:00",
            "realized_pnl": {"amount": "500", "currency": "USD"},
            "fees_paid": {"amount": "3", "currency": "USD"},
            "hold_seconds": 3600,
            "exit_reason": "TAKE_PROFIT",
            "metadata": {},
        },
        {
            "trade_id": {"value": "trade-2"},
            "strategy_id": {"value": "ema_slow"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "SHORT",
            "quantity": {"value": "1"},
            "entry_price": {"value": "110"},
            "exit_price": {"value": "113"},
            "entry_timestamp": "2022-01-04T17:00:00+00:00",
            "exit_timestamp": "2022-01-04T19:00:00+00:00",
            "realized_pnl": {"amount": "-300", "currency": "USD"},
            "fees_paid": {"amount": "2", "currency": "USD"},
            "hold_seconds": 7200,
            "exit_reason": "STOP_LOSS",
            "metadata": {},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_legacy_ledger(run_dir: Path) -> None:
    path = run_dir / "ledger.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "entry_id": {"value": "ledger-1"},
            "timestamp": "2022-01-05T00:00:00+00:00",
            "symbol": {"value": "BTCUSDT"},
            "entry_type": "FILL",
            "amount": {"amount": "0", "currency": "USD"},
            "cash_after": {"amount": "100000", "currency": "USD"},
            "realized_pnl_after": {"amount": "250", "currency": "USD"},
            "fee": {"amount": "1", "currency": "USD"},
            "metadata": {"realized_delta": "250", "strategy_id": "legacy_s"},
        }) + "\n")


def _write_summary(run_dir: Path, fees_paid: float = 5.0) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps({"fees_paid": str(fees_paid), "run_id": "test-run"}),
        encoding="utf-8",
    )


def test_parse_year_month() -> None:
    assert _parse_year_month("2022-03-15T00:00:00+00:00") == (2022, 3)
    assert _parse_year_month("2023-11-01T00:00:00Z") == (2023, 11)


def test_build_equity_curve_assigns_session_labels() -> None:
    calendar = WindowedSessionCalendar(
        calendar_id="sessions",
        timezone_name="UTC",
        session_windows=(),
        out_of_session_label="closed",
    )
    curve = _build_equity_curve(
        [{"timestamp": "2022-01-03T09:00:00+00:00", "equity": 100.0, "cash": 90.0, "fees_paid": 1.0}],
        calendar=calendar,
    )
    assert curve[0]["session_label"] == "closed"


def test_compute_metrics_uses_closed_trade_rows() -> None:
    trade_events = [
        {"timestamp": "2022-01-02T00:00:00+00:00", "pnl": 50.0, "hold_seconds": 60},
        {"timestamp": "2022-01-03T00:00:00+00:00", "pnl": -20.0, "hold_seconds": 120},
        {"timestamp": "2022-01-04T00:00:00+00:00", "pnl": 30.0, "hold_seconds": 180},
    ]
    equity_curve = [
        {"timestamp": "2022-01-01T00:00:00+00:00", "equity": 100.0, "peak_equity": 100.0, "drawdown_abs": 0.0, "drawdown_pct": 0.0},
        {"timestamp": "2022-01-04T00:00:00+00:00", "equity": 160.0, "peak_equity": 160.0, "drawdown_abs": 0.0, "drawdown_pct": 0.0},
    ]
    metrics = _compute_metrics(trade_events, equity_curve, fees_paid=5.0)
    assert metrics.trade_count == 3
    assert metrics.win_count == 2
    assert metrics.loss_count == 1
    assert metrics.avg_hold_seconds == pytest.approx(120.0)
    assert metrics.largest_win == pytest.approx(50.0)
    assert metrics.largest_loss == pytest.approx(-20.0)


def test_compute_period_rows_groups_by_month() -> None:
    trade_events = [
        {"timestamp": "2022-01-10T00:00:00+00:00", "pnl": 100.0, "hold_seconds": 60},
        {"timestamp": "2022-02-05T00:00:00+00:00", "pnl": -30.0, "hold_seconds": 60},
    ]
    equity_curve = [
        {"timestamp": "2022-01-01T00:00:00+00:00", "equity": 1000.0, "peak_equity": 1000.0, "drawdown_abs": 0.0, "drawdown_pct": 0.0},
        {"timestamp": "2022-01-31T00:00:00+00:00", "equity": 1100.0, "peak_equity": 1100.0, "drawdown_abs": 0.0, "drawdown_pct": 0.0},
        {"timestamp": "2022-02-01T00:00:00+00:00", "equity": 1100.0, "peak_equity": 1100.0, "drawdown_abs": 0.0, "drawdown_pct": 0.0},
        {"timestamp": "2022-02-28T00:00:00+00:00", "equity": 1070.0, "peak_equity": 1100.0, "drawdown_abs": 30.0, "drawdown_pct": 2.7},
    ]
    rows = _compute_period_rows(trade_events, equity_curve)
    assert len(rows) == 2
    assert rows[0]["month"] == 1
    assert rows[0]["trade_count"] == 1
    assert rows[1]["month"] == 2
    assert rows[1]["loss_count"] == 1


def test_load_trade_events_prefers_trades_jsonl(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_trades(run_dir)
    events = _load_trade_events(run_dir)
    assert len(events) == 2
    assert events[0]["strategy_id"] == "ema_fast"
    assert events[1]["side"] == "SHORT"


def test_load_trade_events_falls_back_to_ledger(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_legacy_ledger(run_dir)
    events = _load_trade_events(run_dir)
    assert len(events) == 1
    assert events[0]["strategy_id"] == "legacy_s"
    assert events[0]["pnl"] == pytest.approx(250.0)


def test_generate_backtest_report_writes_research_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    _write_manifest(run_dir)
    _write_equity(run_dir, [
        ("2022-01-03T09:00:00+00:00", 100000.0),
        ("2022-01-03T10:00:00+00:00", 100500.0),
        ("2022-01-04T17:00:00+00:00", 100200.0),
        ("2022-02-01T18:00:00+00:00", 101000.0),
        ("2022-02-28T19:00:00+00:00", 102000.0),
    ])
    _write_trades(run_dir)
    _write_summary(run_dir, fees_paid=15.0)

    artifacts = generate_backtest_report(run_dir)

    assert (run_dir / "equity_curve.csv").exists()
    assert (run_dir / "equity_curve.png").exists()
    assert (run_dir / "months.csv").exists()
    assert (run_dir / "years.csv").exists()
    assert (run_dir / "sessions.csv").exists()
    assert "sessions_csv" in artifacts

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert "strategy_attribution" in summary
    assert "ema_fast" in summary["strategy_attribution"]
    assert "long_short_breakdown" in summary
    assert "long" in summary["long_short_breakdown"]
    assert "sessions" in summary
    assert "europe" in summary["sessions"]
    assert "overall" in summary["sessions"]

    with (run_dir / "sessions.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = {row["session_label"] for row in rows}
    assert {"europe", "us"}.issubset(labels)


def test_generate_backtest_report_uses_default_crypto_session_buckets(tmp_path: Path) -> None:
    run_dir = tmp_path / "default_sessions_run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": {"value": "test-run"},
            "app_name": "backtester",
            "mode": "backtest",
            "metadata": {
                "calendar_config": {
                    "kind": "always_open",
                    "calendar_id": "crypto_24x7",
                    "timezone": "UTC",
                    "session_label": "all_session",
                },
            },
        }),
        encoding="utf-8",
    )
    _write_equity(run_dir, [
        ("2022-01-03T01:00:00+00:00", 1000.0),
        ("2022-01-03T09:00:00+00:00", 1010.0),
        ("2022-01-03T13:00:00+00:00", 1020.0),
        ("2022-01-03T21:00:00+00:00", 1015.0),
    ])
    path = run_dir / "trades.jsonl"
    rows = [
        {
            "trade_id": {"value": "trade-1"},
            "strategy_id": {"value": "s1"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "LONG",
            "quantity": {"value": "1"},
            "entry_price": {"value": "100"},
            "exit_price": {"value": "101"},
            "entry_timestamp": "2022-01-03T01:00:00+00:00",
            "exit_timestamp": "2022-01-03T02:00:00+00:00",
            "realized_pnl": {"amount": "10", "currency": "USD"},
            "fees_paid": {"amount": "1", "currency": "USD"},
            "hold_seconds": 3600,
            "exit_reason": "X",
            "metadata": {},
        },
        {
            "trade_id": {"value": "trade-2"},
            "strategy_id": {"value": "s1"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "LONG",
            "quantity": {"value": "1"},
            "entry_price": {"value": "100"},
            "exit_price": {"value": "101"},
            "entry_timestamp": "2022-01-03T09:00:00+00:00",
            "exit_timestamp": "2022-01-03T10:00:00+00:00",
            "realized_pnl": {"amount": "20", "currency": "USD"},
            "fees_paid": {"amount": "1", "currency": "USD"},
            "hold_seconds": 3600,
            "exit_reason": "X",
            "metadata": {},
        },
        {
            "trade_id": {"value": "trade-3"},
            "strategy_id": {"value": "s1"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "LONG",
            "quantity": {"value": "1"},
            "entry_price": {"value": "100"},
            "exit_price": {"value": "101"},
            "entry_timestamp": "2022-01-03T13:00:00+00:00",
            "exit_timestamp": "2022-01-03T14:00:00+00:00",
            "realized_pnl": {"amount": "30", "currency": "USD"},
            "fees_paid": {"amount": "1", "currency": "USD"},
            "hold_seconds": 3600,
            "exit_reason": "X",
            "metadata": {},
        },
        {
            "trade_id": {"value": "trade-4"},
            "strategy_id": {"value": "s1"},
            "symbol": {"value": "BTCUSDT"},
            "venue": {"value": "SIM"},
            "side": "LONG",
            "quantity": {"value": "1"},
            "entry_price": {"value": "100"},
            "exit_price": {"value": "101"},
            "entry_timestamp": "2022-01-03T21:00:00+00:00",
            "exit_timestamp": "2022-01-03T22:00:00+00:00",
            "realized_pnl": {"amount": "-5", "currency": "USD"},
            "fees_paid": {"amount": "1", "currency": "USD"},
            "hold_seconds": 3600,
            "exit_reason": "X",
            "metadata": {},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    _write_summary(run_dir, fees_paid=4.0)

    generate_backtest_report(run_dir)

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert {"overall", "asia", "london", "ny", "out_of_session"} <= set(summary["sessions"].keys())


def test_generate_backtest_report_no_equity_returns_empty(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()
    assert generate_backtest_report(run_dir) == {}


def test_load_equity_rows_reads_snapshots(tmp_path: Path) -> None:
    run_dir = tmp_path / "equity_run"
    run_dir.mkdir()
    _write_equity(run_dir, [("2022-01-01T00:00:00+00:00", 1000.0)])
    rows = _load_equity_rows(run_dir)
    assert rows[0]["equity"] == pytest.approx(1000.0)

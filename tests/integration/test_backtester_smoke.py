from pathlib import Path
import json

from qcore.simulation.backtest import BacktestRunner


def test_backtester_smoke(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "configs/app/backtest_ema_cross.yaml"
    runner = BacktestRunner(config_path=config_path, project_root=project_root, run_id="smoke-test")
    runner.config["run"]["artifacts_root"] = str(tmp_path)

    result = runner.run()

    assert result.summary_path.exists()
    assert (result.run_dir / "fills.jsonl").exists()
    assert (result.run_dir / "equity_curve.csv").exists()
    assert (result.run_dir / "equity_curve.png").exists()
    assert (result.run_dir / "sessions.csv").exists()
    assert result.final_snapshot.balance.equity.amount > 0


def test_backtester_smoke_csv_replay(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "tests/fixtures/data/backtest_ema_cross_csv.json"
    runner = BacktestRunner(config_path=config_path, project_root=project_root, run_id="smoke-test-csv")
    runner.config["run"]["artifacts_root"] = str(tmp_path)

    result = runner.run()

    assert result.summary_path.exists()
    assert (result.run_dir / "fills.jsonl").exists()
    assert (result.run_dir / "equity_curve.csv").exists()
    assert (result.run_dir / "sessions.csv").exists()
    assert result.final_snapshot.balance.equity.amount > 0


def test_backtester_source_timeframe_bracket_exits(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    sample_path = tmp_path / "ema_bracket.csv"
    sample_path.write_text(
        "\n".join([
            "timestamp,open,high,low,close,volume,symbol,venue,timeframe",
            "2026-01-01T00:01:00Z,100,100.2,99.8,100,10,ETHUSDT,SIM,1m",
            "2026-01-01T00:02:00Z,100,100.1,98.9,99,10,ETHUSDT,SIM,1m",
            "2026-01-01T00:03:00Z,99,99.2,97.8,98,10,ETHUSDT,SIM,1m",
            "2026-01-01T00:04:00Z,98,101.2,97.9,101,10,ETHUSDT,SIM,1m",
            "2026-01-01T00:05:00Z,101,103.0,100.5,102.5,10,ETHUSDT,SIM,1m",
        ]),
        encoding="utf-8",
    )
    config_path = project_root / "configs/app/backtest_ema_cross.yaml"
    runner = BacktestRunner(config_path=config_path, project_root=project_root, run_id="smoke-test-brackets")
    runner.config["run"]["artifacts_root"] = str(tmp_path)
    runner.config["data"]["adapter"] = "csv"
    runner.config["data"]["path"] = str(sample_path)
    runner.config["data"].pop("paths", None)
    runner.config["data"]["source_timeframe"] = "1m"
    runner.config["strategies"] = [{
        "kind": "ema_cross",
        "strategy_id": "ema_bracket",
        "input_timeframe": "1m",
        "short_period": 1,
        "long_period": 2,
        "signal_horizon": "1m",
        "stop_loss_fraction": 0.01,
        "take_profit_fraction": 0.015,
    }]
    runner.config["models"] = []
    runner.config["gates"] = []

    result = runner.run()

    fills = [json.loads(line) for line in (result.run_dir / "fills.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(fills) >= 2
    assert any(fill.get("metadata", {}).get("managed_exit") for fill in fills)
    assert (result.run_dir / "sessions.csv").exists()
    ledger = [json.loads(line) for line in (result.run_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(entry.get("metadata", {}).get("fill_metadata", {}).get("exit_reason") == "TAKE_PROFIT" for entry in ledger)

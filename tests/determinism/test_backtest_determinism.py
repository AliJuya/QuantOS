import json
from pathlib import Path

from qcore.simulation.backtest import BacktestRunner


def test_backtest_outputs_are_deterministic(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "configs/app/backtest_ema_cross.yaml"

    runner_a = BacktestRunner(config_path=config_path, project_root=project_root, run_id="det-a")
    runner_a.config["run"]["artifacts_root"] = str(tmp_path / "a")
    result_a = runner_a.run()

    runner_b = BacktestRunner(config_path=config_path, project_root=project_root, run_id="det-b")
    runner_b.config["run"]["artifacts_root"] = str(tmp_path / "b")
    result_b = runner_b.run()

    summary_a = json.loads(result_a.summary_path.read_text(encoding="utf-8"))
    summary_b = json.loads(result_b.summary_path.read_text(encoding="utf-8"))
    fills_a = (result_a.run_dir / "fills.jsonl").read_text(encoding="utf-8")
    fills_b = (result_b.run_dir / "fills.jsonl").read_text(encoding="utf-8")
    equity_a = (result_a.run_dir / "equity.jsonl").read_text(encoding="utf-8")
    equity_b = (result_b.run_dir / "equity.jsonl").read_text(encoding="utf-8")

    summary_a.pop("run_id")
    summary_b.pop("run_id")
    summary_a.pop("artifacts", None)
    summary_b.pop("artifacts", None)

    assert summary_a == summary_b
    assert fills_a == fills_b
    assert equity_a == equity_b

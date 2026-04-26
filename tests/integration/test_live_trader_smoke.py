from pathlib import Path

from qcore.services.runtime import LiveTraderRunner


def test_live_trader_smoke(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "configs/app/live_ema_cross_simulator.yaml"
    runner = LiveTraderRunner(config_path=config_path, project_root=project_root, run_id="live-smoke-test")
    runner.config["run"]["artifacts_root"] = str(tmp_path)

    result = runner.run()

    assert result.summary_path.exists()
    assert (result.run_dir / "fills.jsonl").exists()
    assert result.manifest.event_count > 0
    assert result.final_snapshot.balance.equity.amount > 0

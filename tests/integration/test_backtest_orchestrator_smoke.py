from pathlib import Path

from qcore.simulation.backtest import BacktestOrchestrator


def test_backtest_orchestrator_parameter_mode_smoke(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "configs/app/backtest_ema_cross.yaml"
    orchestrator = BacktestOrchestrator(
        config_path=config_path,
        project_root=project_root,
        run_id="orchestrator-smoke",
    )
    orchestrator.config["run"]["artifacts_root"] = str(tmp_path)
    orchestrator.config["orchestrator"] = {
        "enabled": True,
        "workers": 1,
        "mode": "parameters",
        "parameter_sets": [
            {"name": "fast_3_5", "overrides": {"strategies": [{"kind": "ema_cross", "strategy_id": "s1", "short_period": 3, "long_period": 5, "signal_horizon": "1d"}]}},
            {"name": "fast_2_4", "overrides": {"strategies": [{"kind": "ema_cross", "strategy_id": "s2", "short_period": 2, "long_period": 4, "signal_horizon": "1d"}]}},
        ],
    }

    result = orchestrator.run()

    assert result.summary_path.exists()
    assert result.jobs_csv_path.exists()
    assert len(result.jobs) == 2
    assert all(job.status == "completed" for job in result.jobs)

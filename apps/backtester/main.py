from __future__ import annotations

import argparse
import json
from pathlib import Path

from qcore.kernel.config import load_config
from qcore.simulation.backtest import BacktestOrchestrator, BacktestRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QuantOS backtester.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/app/backtest_ema_cross.yaml"),
        help="Path to the backtest config file.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="QuantOS project root.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Override the generated run id.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    orchestrator_cfg = config.get("orchestrator") or {}
    if orchestrator_cfg.get("enabled"):
        result = BacktestOrchestrator(
            config_path=args.config,
            project_root=args.project_root,
            run_id=args.run_id,
        ).run()
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "run_dir": str(result.run_dir),
                    "summary_path": str(result.summary_path),
                    "jobs_csv_path": str(result.jobs_csv_path),
                    "job_count": len(result.jobs),
                    "completed_jobs": sum(1 for job in result.jobs if job.status == "completed"),
                },
                indent=2,
            )
        )
    else:
        result = BacktestRunner(
            config_path=args.config,
            project_root=args.project_root,
            run_id=args.run_id,
            config=config,
        ).run()
        print(
            json.dumps(
                {
                    "run_id": str(result.manifest.run_id),
                    "run_dir": str(result.run_dir),
                    "summary_path": str(result.summary_path),
                    "ending_equity": str(result.final_snapshot.balance.equity.amount),
                    "trade_count": json.loads(result.summary_path.read_text(encoding="utf-8"))["trade_count"],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qcore.services.runtime import LiveTraderRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QuantOS live trader.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/app/live_ema_cross_simulator.yaml"),
        help="Path to the live trader config file.",
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
    result = LiveTraderRunner(
        config_path=args.config,
        project_root=args.project_root,
        run_id=args.run_id,
    ).run()
    print(
        json.dumps(
            {
                "run_id": str(result.manifest.run_id),
                "run_dir": str(result.run_dir),
                "summary_path": str(result.summary_path),
                "ending_equity": str(result.final_snapshot.balance.equity.amount),
                "event_count": result.manifest.event_count,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

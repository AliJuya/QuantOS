from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Any

from qcore.analytics.reporter import generate_backtest_report
from qcore.domain.types import PortfolioSnapshot, ReplayCheckpoint, RunManifest
from qcore.kernel.config import load_config
from qcore.services.app_builder import BacktestAppBuilder


@dataclass(frozen=True, slots=True)
class BacktestRunResult:
    manifest: RunManifest
    final_snapshot: PortfolioSnapshot
    run_dir: Path
    summary_path: Path
    report_artifacts: dict[str, Path]


class BacktestRunner:
    def __init__(
        self,
        config_path: Path,
        project_root: Path,
        run_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.config_path = config_path.resolve()
        self.project_root = project_root.resolve()
        self.config = config if config is not None else load_config(self.config_path)
        self.run_id = run_id

    def run(self) -> BacktestRunResult:
        runtime = BacktestAppBuilder(
            config=self.config,
            config_path=self.config_path,
            project_root=self.project_root,
            run_id=self.run_id,
        ).build()
        runtime.recorder.write_manifest(runtime.manifest)
        logging_cfg = self._logging_config()
        self._print_start(runtime, logging_cfg)

        event_count = 0
        checkpoint: ReplayCheckpoint | None = None
        last_log_bars = 0
        last_log_time = time.monotonic()
        last_trade_count = runtime.recorder.trade_count
        try:
            for index, bar in enumerate(runtime.source.iter_events()):
                runtime.clock.advance_to(bar.timestamp)
                published = runtime.bus.publish(bar)
                event_count += len(published)
                checkpoint = ReplayCheckpoint(
                    event_index=index,
                    timestamp=bar.timestamp,
                    last_event_type=type(bar).__name__,
                )
                for event in published:
                    runtime.recorder.record_event(event)
                snapshot = runtime.accounting.mark_to_market(bar.timestamp)
                runtime.recorder.record_portfolio_snapshot(snapshot)
                processed_bars = index + 1
                trade_count = runtime.recorder.trade_count
                now_monotonic = time.monotonic()
                should_log = False
                if processed_bars - last_log_bars >= logging_cfg["progress_every_bars"]:
                    should_log = True
                elif now_monotonic - last_log_time >= logging_cfg["progress_every_seconds"]:
                    should_log = True
                elif logging_cfg["log_on_trade"] and trade_count != last_trade_count:
                    should_log = True
                if should_log:
                    self._print_progress(
                        processed_bars=processed_bars,
                        event_count=event_count,
                        timestamp=bar.timestamp,
                        trade_count=trade_count,
                        snapshot=snapshot,
                    )
                    last_log_bars = processed_bars
                    last_log_time = now_monotonic
                    last_trade_count = trade_count

            final_time = runtime.clock.now() or datetime.now(tz=UTC)
            final_snapshot = runtime.accounting.mark_to_market(final_time)
            manifest = replace(
                runtime.manifest,
                completed_at=datetime.now(tz=UTC),
                event_count=event_count,
                replay_checkpoint=checkpoint,
            )
            runtime.recorder.write_manifest(manifest)
            summary_path = runtime.recorder.write_summary(manifest, final_snapshot)
            runtime.recorder.close()

            report_artifacts = generate_backtest_report(runtime.run_dir)
            self._print_complete(
                manifest=manifest,
                snapshot=final_snapshot,
                run_dir=runtime.run_dir,
                summary_path=summary_path,
            )

            return BacktestRunResult(
                manifest=manifest,
                final_snapshot=final_snapshot,
                run_dir=runtime.run_dir,
                summary_path=summary_path,
                report_artifacts=report_artifacts,
            )
        finally:
            runtime.recorder.close()

    def _logging_config(self) -> dict[str, Any]:
        raw = self.config.get("logging") or {}
        progress_every_bars = int(raw.get("progress_every_bars", 10_000))
        progress_every_seconds = float(raw.get("progress_every_seconds", 15))
        return {
            "progress_every_bars": max(1, progress_every_bars),
            "progress_every_seconds": max(1.0, progress_every_seconds),
            "log_on_trade": bool(raw.get("log_on_trade", True)),
        }

    def _print_start(self, runtime: Any, logging_cfg: dict[str, Any]) -> None:
        strategy_ids = [
            str(item.get("strategy_id") or item.get("kind"))
            for item in self.config.get("strategies", [])
        ]
        data_cfg = self.config.get("data") or {}
        locations = data_cfg.get("paths") or [data_cfg.get("path")]
        source_path = ", ".join(str(x) for x in locations if x)
        print(
            "[BACKTEST] "
            f"run_id={runtime.manifest.run_id.value} "
            f"source_tf={data_cfg.get('source_timeframe')} "
            f"strategies={strategy_ids} "
            f"data={source_path}",
            flush=True,
        )
        print(
            "[BACKTEST] "
            f"artifacts={runtime.run_dir} "
            f"progress_every_bars={logging_cfg['progress_every_bars']} "
            f"progress_every_seconds={logging_cfg['progress_every_seconds']} "
            f"log_on_trade={logging_cfg['log_on_trade']}",
            flush=True,
        )

    @staticmethod
    def _print_progress(
        *,
        processed_bars: int,
        event_count: int,
        timestamp: datetime,
        trade_count: int,
        snapshot: PortfolioSnapshot,
    ) -> None:
        print(
            "[BACKTEST] "
            f"bars={processed_bars} "
            f"events={event_count} "
            f"ts={timestamp.isoformat()} "
            f"trades={trade_count} "
            f"equity={snapshot.balance.equity.amount} "
            f"cash={snapshot.balance.cash.amount} "
            f"realized={snapshot.realized_pnl.amount} "
            f"unrealized={snapshot.unrealized_pnl.amount} "
            f"positions={len(snapshot.positions)}",
            flush=True,
        )

    @staticmethod
    def _print_complete(
        *,
        manifest: RunManifest,
        snapshot: PortfolioSnapshot,
        run_dir: Path,
        summary_path: Path,
    ) -> None:
        print(
            "[BACKTEST] "
            f"complete run_id={manifest.run_id.value} "
            f"events={manifest.event_count} "
            f"ending_equity={snapshot.balance.equity.amount} "
            f"net_pnl={snapshot.net_pnl.amount} "
            f"fees={snapshot.balance.fees_paid.amount}",
            flush=True,
        )
        print(
            "[BACKTEST] "
            f"summary={summary_path} "
            f"run_dir={run_dir}",
            flush=True,
        )

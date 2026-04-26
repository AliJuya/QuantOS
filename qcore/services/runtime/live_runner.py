from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from qcore.domain.events import BarCloseEvent, FillEvent
from qcore.domain.types import PortfolioSnapshot, RunManifest
from qcore.kernel.config import load_config
from qcore.services.app_builder import LiveAppBuilder


@dataclass(slots=True)
class _LiveRunObserver:
    runtime: object
    event_count: int = 0
    last_event_timestamp: datetime | None = None
    last_event_type: str | None = None

    def on_event(self, event: object) -> None:
        self.event_count += 1
        self.runtime.recorder.record_event(event)
        timestamp = getattr(event, "timestamp", None)
        if isinstance(timestamp, datetime):
            self.last_event_timestamp = timestamp
        self.last_event_type = type(event).__name__

    def on_bar_close(self, event: BarCloseEvent) -> None:
        snapshot = self.runtime.accounting.mark_to_market(event.timestamp)
        self.runtime.recorder.record_portfolio_snapshot(snapshot)

    def on_fill(self, event: FillEvent) -> None:
        snapshot = self.runtime.accounting.mark_to_market(event.timestamp)
        self.runtime.recorder.record_portfolio_snapshot(snapshot)


@dataclass(frozen=True, slots=True)
class LiveRunResult:
    manifest: RunManifest
    final_snapshot: PortfolioSnapshot
    run_dir: Path
    summary_path: Path


class LiveTraderRunner:
    def __init__(self, config_path: Path, project_root: Path, run_id: str | None = None) -> None:
        self.config_path = config_path.resolve()
        self.project_root = project_root.resolve()
        self.config = load_config(self.config_path)
        self.run_id = run_id

    def run(self) -> LiveRunResult:
        runtime = LiveAppBuilder(
            config=self.config,
            config_path=self.config_path,
            project_root=self.project_root,
            run_id=self.run_id,
        ).build()
        observer = _LiveRunObserver(runtime=runtime)
        runtime.bus.subscribe(object, observer.on_event)
        runtime.bus.subscribe(BarCloseEvent, observer.on_bar_close)
        runtime.bus.subscribe(FillEvent, observer.on_fill)

        runtime.recorder.write_manifest(runtime.manifest)
        try:
            runtime.ingestion.start()
        except KeyboardInterrupt:
            pass
        finally:
            runtime.ingestion.stop()
            runtime.recorder.close()

        final_time = observer.last_event_timestamp or datetime.now(tz=UTC)
        final_snapshot = runtime.accounting.mark_to_market(final_time)
        manifest = replace(
            runtime.manifest,
            completed_at=datetime.now(tz=UTC),
            event_count=observer.event_count,
            replay_checkpoint=None,
        )
        runtime.recorder.write_manifest(manifest)
        summary_path = runtime.recorder.write_summary(manifest, final_snapshot)
        return LiveRunResult(
            manifest=manifest,
            final_snapshot=final_snapshot,
            run_dir=runtime.run_dir,
            summary_path=summary_path,
        )

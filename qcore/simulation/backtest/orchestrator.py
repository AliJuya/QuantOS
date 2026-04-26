from __future__ import annotations

import csv
import json
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qcore.kernel.config import load_config, normalize_config
from qcore.simulation.backtest.runner import BacktestRunner


@dataclass(frozen=True, slots=True)
class BacktestJobResult:
    name: str
    run_id: str
    status: str
    run_dir: Path | None
    summary_path: Path | None
    ending_equity: float | None
    pnl: float | None
    trade_count: int | None
    winrate: float | None
    max_drawdown: float | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestOrchestratorResult:
    run_id: str
    run_dir: Path
    summary_path: Path
    jobs_csv_path: Path
    jobs: tuple[BacktestJobResult, ...]


class BacktestOrchestrator:
    def __init__(self, config_path: Path, project_root: Path, run_id: str | None = None) -> None:
        self.config_path = config_path.resolve()
        self.project_root = project_root.resolve()
        self.config = load_config(self.config_path)
        self.run_id = run_id or self.config.get("run", {}).get("run_id") or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    def run(self) -> BacktestOrchestratorResult:
        orchestrator_cfg = self.config.get("orchestrator") or {}
        mode = str(orchestrator_cfg.get("mode", "parameters")).strip().lower()
        workers = max(1, int(orchestrator_cfg.get("workers", 1)))

        run_dir = self._resolve_path(self.config["run"]["artifacts_root"]) / self.run_id
        jobs_dir = run_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        jobs = self._build_jobs(mode=mode, jobs_dir=jobs_dir)
        if workers <= 1 or len(jobs) <= 1:
            results = tuple(_run_backtest_job(job) for job in jobs)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = tuple(pool.map(_run_backtest_job, jobs))

        jobs_csv_path = self._write_jobs_csv(run_dir, results)
        summary_path = self._write_summary(run_dir, mode, workers, results)
        return BacktestOrchestratorResult(
            run_id=self.run_id,
            run_dir=run_dir,
            summary_path=summary_path,
            jobs_csv_path=jobs_csv_path,
            jobs=results,
        )

    def _build_jobs(self, *, mode: str, jobs_dir: Path) -> tuple[dict[str, Any], ...]:
        base_config = deepcopy(self.config)
        base_config.pop("orchestrator", None)
        base_config.setdefault("run", {})
        base_config["run"]["artifacts_root"] = str(jobs_dir)

        orchestrator_cfg = self.config.get("orchestrator") or {}
        jobs: list[dict[str, Any]] = []

        if mode == "parameters":
            parameter_sets = orchestrator_cfg.get("parameter_sets") or orchestrator_cfg.get("jobs") or []
            if not isinstance(parameter_sets, list) or not parameter_sets:
                raise ValueError("orchestrator.parameters mode requires non-empty parameter_sets")
            for idx, item in enumerate(parameter_sets, start=1):
                if not isinstance(item, dict):
                    raise ValueError("parameter_sets items must be mappings")
                name = str(item.get("name", f"params_{idx:02d}"))
                overrides = item.get("overrides", item)
                if not isinstance(overrides, dict):
                    raise ValueError("parameter set overrides must be a mapping")
                child = _deep_merge(base_config, overrides)
                child_run_id = f"{self.run_id}__{_slugify(name)}"
                jobs.append(_job_spec(
                    name=name,
                    run_id=child_run_id,
                    config=normalize_config(child),
                    config_path=self.config_path,
                    project_root=self.project_root,
                ))
            return tuple(jobs)

        if mode == "symbols":
            symbols = orchestrator_cfg.get("symbols") or []
            if not isinstance(symbols, list) or not symbols:
                raise ValueError("orchestrator.symbols mode requires non-empty symbols")
            for symbol in symbols:
                symbol_value = str(symbol)
                child = deepcopy(base_config)
                child.setdefault("run", {})["symbol"] = symbol_value
                child.setdefault("data", {})["default_symbol"] = symbol_value
                child["data"] = _format_symbol_paths(child["data"], symbol_value)
                child_run_id = f"{self.run_id}__{_slugify(symbol_value)}"
                jobs.append(_job_spec(
                    name=symbol_value,
                    run_id=child_run_id,
                    config=normalize_config(child),
                    config_path=self.config_path,
                    project_root=self.project_root,
                ))
            return tuple(jobs)

        raise ValueError(f"unsupported orchestrator mode: {mode}")

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    @staticmethod
    def _write_jobs_csv(run_dir: Path, results: tuple[BacktestJobResult, ...]) -> Path:
        path = run_dir / "jobs.csv"
        rows = [
            {
                "name": result.name,
                "run_id": result.run_id,
                "status": result.status,
                "run_dir": "" if result.run_dir is None else str(result.run_dir),
                "summary_path": "" if result.summary_path is None else str(result.summary_path),
                "ending_equity": "" if result.ending_equity is None else result.ending_equity,
                "pnl": "" if result.pnl is None else result.pnl,
                "trade_count": "" if result.trade_count is None else result.trade_count,
                "winrate": "" if result.winrate is None else result.winrate,
                "max_drawdown": "" if result.max_drawdown is None else result.max_drawdown,
                "error": result.error or "",
            }
            for result in results
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [
                "name", "run_id", "status", "run_dir", "summary_path",
                "ending_equity", "pnl", "trade_count", "winrate", "max_drawdown", "error",
            ])
            writer.writeheader()
            writer.writerows(rows)
        return path

    @staticmethod
    def _write_summary(run_dir: Path, mode: str, workers: int, results: tuple[BacktestJobResult, ...]) -> Path:
        path = run_dir / "orchestrator_summary.json"
        completed = [result for result in results if result.status == "completed"]
        child_manifests = []
        for result in completed:
            if result.run_dir is None:
                continue
            manifest_path = result.run_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            child_manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))

        app_names = sorted({manifest.get("app_name") for manifest in child_manifests if manifest.get("app_name")})
        modes = sorted({manifest.get("mode") for manifest in child_manifests if manifest.get("mode")})
        config_digests = sorted({manifest.get("config_digest") for manifest in child_manifests if manifest.get("config_digest")})
        payload = {
            "mode": mode,
            "workers": workers,
            "job_count": len(results),
            "completed_jobs": len(completed),
            "failed_jobs": len(results) - len(completed),
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "merge_semantics": "comparison_only",
            "aggregate_simple": {
                "total_pnl": round(sum(result.pnl or 0.0 for result in completed), 4),
                "total_trade_count": sum(result.trade_count or 0 for result in completed),
                "max_child_drawdown": round(max((result.max_drawdown or 0.0) for result in completed), 4) if completed else 0.0,
            },
            "child_manifest_consistency": {
                "app_names": app_names,
                "modes": modes,
                "config_digests": config_digests,
                "homogeneous_app_name": len(app_names) <= 1,
                "homogeneous_mode": len(modes) <= 1,
            },
            "note": "aggregate_simple is a comparison summary, not a portfolio-equivalent merged backtest",
            "jobs": [
                {
                    "name": result.name,
                    "run_id": result.run_id,
                    "status": result.status,
                    "run_dir": None if result.run_dir is None else str(result.run_dir),
                    "summary_path": None if result.summary_path is None else str(result.summary_path),
                    "ending_equity": result.ending_equity,
                    "pnl": result.pnl,
                    "trade_count": result.trade_count,
                    "winrate": result.winrate,
                    "max_drawdown": result.max_drawdown,
                    "error": result.error,
                }
                for result in results
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


def _job_spec(
    *,
    name: str,
    run_id: str,
    config: dict[str, Any],
    config_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    return {
        "name": name,
        "run_id": run_id,
        "config": config,
        "config_path": str(config_path),
        "project_root": str(project_root),
    }


def _run_backtest_job(job: dict[str, Any]) -> BacktestJobResult:
    try:
        runner = BacktestRunner(
            config_path=Path(job["config_path"]),
            project_root=Path(job["project_root"]),
            run_id=str(job["run_id"]),
            config=job["config"],
        )
        result = runner.run()
        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        return BacktestJobResult(
            name=str(job["name"]),
            run_id=str(job["run_id"]),
            status="completed",
            run_dir=result.run_dir,
            summary_path=result.summary_path,
            ending_equity=float(summary.get("ending_equity", 0.0)),
            pnl=float(summary.get("pnl", 0.0)),
            trade_count=int(summary.get("trade_count", 0)),
            winrate=float(summary.get("winrate", 0.0)),
            max_drawdown=float(summary.get("max_drawdown", 0.0)),
        )
    except Exception as exc:
        return BacktestJobResult(
            name=str(job["name"]),
            run_id=str(job["run_id"]),
            status="failed",
            run_dir=None,
            summary_path=None,
            ending_equity=None,
            pnl=None,
            trade_count=None,
            winrate=None,
            max_drawdown=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _format_symbol_paths(data_config: dict[str, Any], symbol: str) -> dict[str, Any]:
    updated = deepcopy(data_config)
    if "path" in updated and isinstance(updated["path"], str):
        updated["path"] = updated["path"].format(symbol=symbol)
    if "paths" in updated:
        updated["paths"] = [
            item.format(symbol=symbol) if isinstance(item, str) else item
            for item in updated["paths"]
        ]
    return updated


def _slugify(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned.strip("_") or "job"

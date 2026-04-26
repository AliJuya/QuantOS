from __future__ import annotations

import csv
import json
import struct
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from qcore.data.calendars import AlwaysOpenCalendar, TradingCalendarProtocol
from qcore.registry import build_calendar


@dataclass(frozen=True)
class BacktestMetrics:
    starting_equity: float
    ending_equity: float
    pnl: float
    fees_paid: float
    trade_count: int
    win_count: int
    loss_count: int
    winrate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    drawdown_pct: float
    avg_hold_seconds: float
    largest_win: float
    largest_loss: float


@dataclass(frozen=True)
class SessionBucket:
    label: str
    start_hour: int
    end_hour: int


@dataclass(frozen=True)
class ReportingSessionConfig:
    timezone_name: str
    buckets: tuple[SessionBucket, ...]
    out_of_session_label: str


DEFAULT_REPORTING_SESSION_CONFIG = ReportingSessionConfig(
    timezone_name="UTC",
    buckets=(
        SessionBucket(label="asia", start_hour=0, end_hour=8),
        SessionBucket(label="london", start_hour=8, end_hour=12),
        SessionBucket(label="ny", start_hour=12, end_hour=20),
    ),
    out_of_session_label="out_of_session",
)


def generate_backtest_report(run_dir: Path) -> dict[str, Path]:
    equity_rows = _load_equity_rows(run_dir)
    if not equity_rows:
        return {}

    manifest = _load_manifest(run_dir)
    calendar = _build_reporting_calendar(manifest)
    session_config = _build_reporting_session_config(manifest)
    trade_events = _load_trade_events(run_dir)
    fees_paid = _load_fees_paid(run_dir)
    equity_curve = _build_equity_curve(equity_rows, calendar=calendar)
    metrics = _compute_metrics(trade_events, equity_curve, fees_paid)
    month_rows = _compute_period_rows(trade_events, equity_curve)
    year_rows = _compute_year_rows(trade_events, equity_curve)
    session_rows = _compute_session_rows(
        trade_events,
        metrics=metrics,
        starting_equity=metrics.starting_equity,
        session_config=session_config,
    )
    strategy_rows = _compute_group_rows(trade_events, key="strategy_id")
    long_short_rows = _compute_group_rows(trade_events, key="side")

    artifacts: dict[str, Path] = {
        "manifest_json": run_dir / "manifest.json",
        "summary_json": run_dir / "summary.json",
        "trades_jsonl": run_dir / "trades.jsonl",
        "fills_jsonl": run_dir / "fills.jsonl",
        "equity_curve_csv": _write_equity_curve_csv(equity_curve, run_dir),
        "equity_curve_png": _write_equity_curve_png(equity_curve, metrics, run_dir),
        "months_csv": _write_months_csv(month_rows, run_dir),
        "years_csv": _write_years_csv(year_rows, run_dir),
        "sessions_csv": _write_sessions_csv(session_rows, run_dir),
    }

    _patch_summary(
        run_dir,
        metrics=metrics,
        artifacts=artifacts,
        strategy_rows=strategy_rows,
        long_short_rows=long_short_rows,
        session_rows=session_rows,
        calendar=calendar,
        session_config=session_config,
    )
    return artifacts


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_reporting_calendar(manifest: dict[str, Any]) -> TradingCalendarProtocol:
    metadata = manifest.get("metadata") or {}
    cfg = metadata.get("calendar_config") or {}
    if not isinstance(cfg, dict):
        return AlwaysOpenCalendar()
    try:
        return build_calendar(cfg)
    except Exception:
        return AlwaysOpenCalendar()


def _build_reporting_session_config(manifest: dict[str, Any]) -> ReportingSessionConfig:
    metadata = manifest.get("metadata") or {}
    reporting_cfg = metadata.get("reporting_config") or {}
    if isinstance(reporting_cfg, dict):
        configured = _session_config_from_dict(reporting_cfg)
        if configured is not None:
            return configured

    calendar_cfg = metadata.get("calendar_config") or {}
    if isinstance(calendar_cfg, dict) and str(calendar_cfg.get("kind")) == "windowed":
        configured = _session_config_from_windowed_calendar(calendar_cfg)
        if configured is not None:
            return configured

    return DEFAULT_REPORTING_SESSION_CONFIG


def _session_config_from_dict(raw: dict[str, Any]) -> ReportingSessionConfig | None:
    buckets = raw.get("session_buckets")
    if not isinstance(buckets, list) or not buckets:
        return None
    parsed = _parse_session_buckets(buckets)
    if not parsed:
        return None
    timezone_name = str(raw.get("session_timezone") or raw.get("timezone") or "UTC")
    out_of_session_label = str(raw.get("out_of_session_label") or "out_of_session")
    return ReportingSessionConfig(
        timezone_name=timezone_name,
        buckets=tuple(parsed),
        out_of_session_label=out_of_session_label,
    )


def _session_config_from_windowed_calendar(raw: dict[str, Any]) -> ReportingSessionConfig | None:
    windows = raw.get("windows")
    if not isinstance(windows, list) or not windows:
        return None
    parsed = _parse_session_buckets(windows)
    if not parsed:
        return None
    return ReportingSessionConfig(
        timezone_name=str(raw.get("timezone") or "UTC"),
        buckets=tuple(parsed),
        out_of_session_label=str(raw.get("out_of_session_label") or "out_of_session"),
    )


def _parse_session_buckets(rows: list[dict[str, Any]]) -> list[SessionBucket]:
    buckets: list[SessionBucket] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        start_hour = row.get("start_hour")
        end_hour = row.get("end_hour")
        if not label or start_hour is None or end_hour is None:
            continue
        buckets.append(
            SessionBucket(
                label=label,
                start_hour=int(start_hour) % 24,
                end_hour=int(end_hour) % 24,
            )
        )
    return buckets


def _session_label_for_timestamp(timestamp: datetime, config: ReportingSessionConfig) -> str:
    try:
        tz = ZoneInfo(config.timezone_name)
    except ZoneInfoNotFoundError:
        tz = UTC
    localized = timestamp.astimezone(tz)
    hour = int(localized.hour)
    for bucket in config.buckets:
        if _hour_in_bucket(hour, bucket):
            return bucket.label
    return config.out_of_session_label


def _hour_in_bucket(hour: int, bucket: SessionBucket) -> bool:
    if bucket.start_hour == bucket.end_hour:
        return True
    if bucket.start_hour < bucket.end_hour:
        return bucket.start_hour <= hour < bucket.end_hour
    return hour >= bucket.start_hour or hour < bucket.end_hour


def _load_equity_rows(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "equity.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append({
                "timestamp": obj["timestamp"],
                "equity": float(obj["balance"]["equity"]["amount"]),
                "cash": float(obj["balance"]["cash"]["amount"]),
                "fees_paid": float(obj["balance"]["fees_paid"]["amount"]),
            })
    return rows


def _load_trade_events(run_dir: Path) -> list[dict[str, Any]]:
    trades_path = run_dir / "trades.jsonl"
    if trades_path.exists():
        rows: list[dict[str, Any]] = []
        with trades_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                rows.append({
                    "trade_id": _nested_value(obj.get("trade_id")),
                    "strategy_id": _nested_value(obj.get("strategy_id")),
                    "symbol": _nested_value(obj.get("symbol")),
                    "venue": _nested_value(obj.get("venue")),
                    "side": str(obj.get("side", "UNKNOWN")),
                    "entry_timestamp": obj.get("entry_timestamp"),
                    "exit_timestamp": obj.get("exit_timestamp"),
                    "timestamp": obj.get("exit_timestamp"),
                    "pnl": float(obj["realized_pnl"]["amount"]),
                    "fees_paid": float(obj["fees_paid"]["amount"]),
                    "hold_seconds": int(obj.get("hold_seconds") or 0),
                    "exit_reason": obj.get("exit_reason"),
                })
        return rows

    ledger_path = run_dir / "ledger.jsonl"
    if not ledger_path.exists():
        return []
    rows = []
    with ledger_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            raw = obj.get("metadata", {}).get("realized_delta") or "0"
            pnl = float(raw)
            if pnl == 0.0:
                continue
            rows.append({
                "trade_id": None,
                "strategy_id": obj.get("metadata", {}).get("strategy_id"),
                "symbol": _nested_value(obj.get("symbol")),
                "venue": None,
                "side": "UNKNOWN",
                "entry_timestamp": obj["timestamp"],
                "exit_timestamp": obj["timestamp"],
                "timestamp": obj["timestamp"],
                "pnl": pnl,
                "fees_paid": float(obj.get("fee", {}).get("amount", 0.0)),
                "hold_seconds": 0,
                "exit_reason": None,
            })
    return rows


def _load_fees_paid(run_dir: Path) -> float:
    path = run_dir / "summary.json"
    if not path.exists():
        return 0.0
    obj = json.loads(path.read_text(encoding="utf-8"))
    return float(obj.get("fees_paid") or "0")


def _build_equity_curve(
    equity_rows: list[dict[str, Any]],
    calendar: TradingCalendarProtocol | None = None,
) -> list[dict[str, Any]]:
    if not equity_rows:
        return []
    peak = equity_rows[0]["equity"]
    curve: list[dict[str, Any]] = []
    for row in equity_rows:
        equity = row["equity"]
        if equity > peak:
            peak = equity
        drawdown_abs = peak - equity
        drawdown_pct = (drawdown_abs / peak * 100.0) if peak > 0 else 0.0
        session_label = None
        if calendar is not None:
            session_label = calendar.session_context(_parse_timestamp(row["timestamp"])).session_label
        curve.append({
            "timestamp": row["timestamp"],
            "equity": round(equity, 4),
            "cash": round(row.get("cash", 0.0), 4),
            "fees_paid": round(row.get("fees_paid", 0.0), 4),
            "peak_equity": round(peak, 4),
            "drawdown_abs": round(drawdown_abs, 4),
            "drawdown_pct": round(drawdown_pct, 4),
            "session_label": session_label,
        })
    return curve


def _compute_metrics(
    trade_events: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    fees_paid: float,
) -> BacktestMetrics:
    trade_stats = _trade_statistics(trade_events)
    starting_equity = equity_curve[0]["equity"] if equity_curve else 0.0
    ending_equity = equity_curve[-1]["equity"] if equity_curve else 0.0
    max_drawdown = max((row["drawdown_abs"] for row in equity_curve), default=0.0)
    drawdown_pct = max((row["drawdown_pct"] for row in equity_curve), default=0.0)
    return BacktestMetrics(
        starting_equity=round(starting_equity, 4),
        ending_equity=round(ending_equity, 4),
        pnl=round(ending_equity - starting_equity, 4),
        fees_paid=round(fees_paid, 4),
        trade_count=trade_stats["trade_count"],
        win_count=trade_stats["win_count"],
        loss_count=trade_stats["loss_count"],
        winrate=trade_stats["winrate"],
        avg_win=trade_stats["avg_win"],
        avg_loss=trade_stats["avg_loss"],
        profit_factor=trade_stats["profit_factor"],
        max_drawdown=round(max_drawdown, 4),
        drawdown_pct=round(drawdown_pct, 4),
        avg_hold_seconds=trade_stats["avg_hold_seconds"],
        largest_win=trade_stats["largest_win"],
        largest_loss=trade_stats["largest_loss"],
    )


def _trade_statistics(
    trade_events: list[dict[str, Any]],
    *,
    fees_paid_override: float | None = None,
) -> dict[str, Any]:
    pnls = [float(event["pnl"]) for event in trade_events]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    trade_count = len(trade_events)
    win_count = len(wins)
    loss_count = len(losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    total_hold_seconds = sum(int(event.get("hold_seconds") or 0) for event in trade_events)
    fees_paid = fees_paid_override if fees_paid_override is not None else sum(float(event.get("fees_paid") or 0.0) for event in trade_events)
    return {
        "pnl": round(sum(pnls), 4),
        "fees_paid": round(fees_paid, 4),
        "trade_count": trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "winrate": round((win_count / trade_count * 100.0) if trade_count else 0.0, 2),
        "avg_win": round(sum(wins) / win_count, 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / loss_count, 4) if losses else 0.0,
        "profit_factor": round((gross_profit / gross_loss) if gross_loss > 0 else 0.0, 4),
        "avg_hold_seconds": round((total_hold_seconds / trade_count) if trade_count else 0.0, 2),
        "largest_win": round(max(wins), 4) if wins else 0.0,
        "largest_loss": round(min(losses), 4) if losses else 0.0,
    }


def _parse_year_month(timestamp: str) -> tuple[int, int]:
    dt = _parse_timestamp(timestamp)
    return dt.year, dt.month


def _compute_period_rows(
    trade_events: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not equity_curve:
        return []

    period_equity: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in equity_curve:
        period_equity.setdefault(_parse_year_month(row["timestamp"]), []).append(row)

    period_trades: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for event in trade_events:
        period_trades.setdefault(_parse_year_month(event["timestamp"]), []).append(event)

    rows: list[dict[str, Any]] = []
    for year, month in sorted(period_equity):
        eq_rows = period_equity[(year, month)]
        trade_rows = period_trades.get((year, month), [])
        stats = _trade_statistics(trade_rows)
        peak = eq_rows[0]["equity"]
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        for row in eq_rows:
            if row["equity"] > peak:
                peak = row["equity"]
            drawdown_abs = peak - row["equity"]
            drawdown_pct = (drawdown_abs / peak * 100.0) if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown_abs)
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        rows.append({
            "year": year,
            "month": month,
            "starting_equity": round(eq_rows[0]["equity"], 4),
            "ending_equity": round(eq_rows[-1]["equity"], 4),
            "net_pnl": round(eq_rows[-1]["equity"] - eq_rows[0]["equity"], 4),
            "trade_count": stats["trade_count"],
            "win_count": stats["win_count"],
            "loss_count": stats["loss_count"],
            "winrate": stats["winrate"],
            "avg_win": stats["avg_win"],
            "avg_loss": stats["avg_loss"],
            "profit_factor": stats["profit_factor"],
            "max_drawdown": round(max_drawdown, 4),
            "drawdown_pct": round(max_drawdown_pct, 4),
        })
    return rows


def _compute_year_rows(
    trade_events: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not equity_curve:
        return []

    year_equity: dict[int, list[dict[str, Any]]] = {}
    for row in equity_curve:
        year = _parse_timestamp(row["timestamp"]).year
        year_equity.setdefault(year, []).append(row)

    year_trades: dict[int, list[dict[str, Any]]] = {}
    for event in trade_events:
        year = _parse_timestamp(event["timestamp"]).year
        year_trades.setdefault(year, []).append(event)

    year_rows: list[dict[str, Any]] = []
    for year in sorted(year_equity):
        eq_rows = year_equity[year]
        stats = _trade_statistics(year_trades.get(year, []))
        year_rows.append({
            "year": year,
            "starting_equity": round(eq_rows[0]["equity"], 4),
            "ending_equity": round(eq_rows[-1]["equity"], 4),
            "net_pnl": round(eq_rows[-1]["equity"] - eq_rows[0]["equity"], 4),
            "trade_count": stats["trade_count"],
            "win_count": stats["win_count"],
            "loss_count": stats["loss_count"],
            "winrate": stats["winrate"],
            "avg_win": stats["avg_win"],
            "avg_loss": stats["avg_loss"],
            "profit_factor": stats["profit_factor"],
            "max_drawdown": round(max(float(row["drawdown_abs"]) for row in eq_rows), 4),
            "drawdown_pct": round(max(float(row["drawdown_pct"]) for row in eq_rows), 4),
        })
    return year_rows


def _compute_group_rows(
    trade_events: list[dict[str, Any]],
    *,
    key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in trade_events:
        raw = event.get(key)
        if raw is None or raw == "":
            value = "unattributed"
        else:
            value = str(raw).lower() if key == "side" else str(raw)
        grouped.setdefault(value, []).append(event)

    rows: dict[str, dict[str, Any]] = {}
    for group_key in sorted(grouped):
        stats = _trade_statistics(grouped[group_key])
        rows[group_key] = stats
    return rows


def _compute_session_rows(
    trade_events: list[dict[str, Any]],
    *,
    metrics: BacktestMetrics,
    starting_equity: float,
    session_config: ReportingSessionConfig,
) -> list[dict[str, Any]]:
    trade_groups: dict[str, list[dict[str, Any]]] = {
        bucket.label: [] for bucket in session_config.buckets
    }
    trade_groups.setdefault(session_config.out_of_session_label, [])
    for trade in trade_events:
        entry_timestamp = trade.get("entry_timestamp") or trade.get("timestamp")
        session_label = _session_label_for_timestamp(_parse_timestamp(entry_timestamp), session_config)
        trade_groups.setdefault(session_label, []).append(trade)

    rows: list[dict[str, Any]] = []
    rows.append({
        "session_label": "overall",
        "pnl": metrics.pnl,
        "fees_paid": metrics.fees_paid,
        "trade_count": metrics.trade_count,
        "win_count": metrics.win_count,
        "loss_count": metrics.loss_count,
        "winrate": metrics.winrate,
        "avg_win": metrics.avg_win,
        "avg_loss": metrics.avg_loss,
        "profit_factor": metrics.profit_factor,
        "avg_hold_seconds": metrics.avg_hold_seconds,
        "largest_win": metrics.largest_win,
        "largest_loss": metrics.largest_loss,
        "max_drawdown": metrics.max_drawdown,
        "drawdown_pct": metrics.drawdown_pct,
    })

    ordered_labels = [bucket.label for bucket in session_config.buckets] + [session_config.out_of_session_label]
    for session_label in ordered_labels:
        trade_stats = _trade_statistics(trade_groups.get(session_label, []))
        max_drawdown, drawdown_pct = _trade_curve_drawdown(
            trade_groups.get(session_label, []),
            starting_equity=starting_equity,
        )
        rows.append({
            "session_label": session_label,
            "pnl": round(trade_stats["pnl"] - trade_stats["fees_paid"], 4),
            "fees_paid": trade_stats["fees_paid"],
            "trade_count": trade_stats["trade_count"],
            "win_count": trade_stats["win_count"],
            "loss_count": trade_stats["loss_count"],
            "winrate": trade_stats["winrate"],
            "avg_win": trade_stats["avg_win"],
            "avg_loss": trade_stats["avg_loss"],
            "profit_factor": trade_stats["profit_factor"],
            "avg_hold_seconds": trade_stats["avg_hold_seconds"],
            "largest_win": trade_stats["largest_win"],
            "largest_loss": trade_stats["largest_loss"],
            "max_drawdown": round(max_drawdown, 4),
            "drawdown_pct": round(drawdown_pct, 4),
        })
    return rows


def _trade_curve_drawdown(trades: list[dict[str, Any]], *, starting_equity: float) -> tuple[float, float]:
    if not trades:
        return 0.0, 0.0
    equity = float(starting_equity)
    peak = float(starting_equity)
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for trade in sorted(trades, key=lambda item: item.get("timestamp") or item.get("exit_timestamp") or ""):
        equity += float(trade.get("pnl") or 0.0) - float(trade.get("fees_paid") or 0.0)
        if equity > peak:
            peak = equity
        drawdown_abs = peak - equity
        drawdown_pct = (drawdown_abs / peak * 100.0) if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown_abs)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
    return max_drawdown, max_drawdown_pct


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_equity_curve_csv(equity_curve: list[dict[str, Any]], run_dir: Path) -> Path:
    fieldnames = ["timestamp", "equity", "cash", "fees_paid", "peak_equity", "drawdown_abs", "drawdown_pct", "session_label"]
    return _write_csv(run_dir / "equity_curve.csv", equity_curve, fieldnames)


def _write_months_csv(rows: list[dict[str, Any]], run_dir: Path) -> Path:
    fieldnames = ["year", "month", "starting_equity", "ending_equity", "net_pnl", "trade_count", "win_count", "loss_count", "winrate", "avg_win", "avg_loss", "profit_factor", "max_drawdown", "drawdown_pct"]
    return _write_csv(run_dir / "months.csv", rows, fieldnames)


def _write_years_csv(rows: list[dict[str, Any]], run_dir: Path) -> Path:
    fieldnames = ["year", "starting_equity", "ending_equity", "net_pnl", "trade_count", "win_count", "loss_count", "winrate", "avg_win", "avg_loss", "profit_factor", "max_drawdown", "drawdown_pct"]
    return _write_csv(run_dir / "years.csv", rows, fieldnames)


def _write_sessions_csv(rows: list[dict[str, Any]], run_dir: Path) -> Path:
    fieldnames = ["session_label", "pnl", "fees_paid", "trade_count", "win_count", "loss_count", "winrate", "avg_win", "avg_loss", "profit_factor", "avg_hold_seconds", "largest_win", "largest_loss", "max_drawdown", "drawdown_pct"]
    return _write_csv(run_dir / "sessions.csv", rows, fieldnames)


def _write_equity_curve_png(
    equity_curve: list[dict[str, Any]],
    metrics: BacktestMetrics,
    run_dir: Path,
) -> Path:
    path = run_dir / "equity_curve.png"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        timestamps = [_parse_timestamp(row["timestamp"]) for row in equity_curve]
        equities = [row["equity"] for row in equity_curve]
        peaks = [row["peak_equity"] for row in equity_curve]
        drawdowns = [row["drawdown_abs"] for row in equity_curve]

        fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(14, 8), dpi=120, sharex=True)
        ax_eq.plot(timestamps, equities, color="#0f172a", linewidth=1.6, label="Equity")
        ax_eq.plot(timestamps, peaks, color="#94a3b8", linewidth=1.0, alpha=0.50, label="Peak")
        ax_eq.set_ylabel("Equity")
        ax_eq.legend(loc="upper left", fontsize=8)
        ax_eq.set_title(
            f"PnL: {metrics.pnl:+.2f} | Trades: {metrics.trade_count} | Winrate: {metrics.winrate:.1f}% | "
            f"Max DD: {metrics.max_drawdown:.2f} ({metrics.drawdown_pct:.1f}%) | PF: {metrics.profit_factor:.2f}",
            fontsize=9,
        )
        ax_eq.grid(True, alpha=0.3)

        ax_dd.fill_between(timestamps, drawdowns, color="#dc2626", alpha=0.35, label="Drawdown")
        ax_dd.set_ylabel("Drawdown")
        ax_dd.set_xlabel("Date")
        ax_dd.legend(loc="upper right", fontsize=8)
        ax_dd.grid(True, alpha=0.3)
        ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()

        plt.tight_layout()
        plt.savefig(path, bbox_inches="tight")
        plt.close(fig)
    except ImportError:
        _write_simple_equity_png(path, [row["equity"] for row in equity_curve])
    return path


def _patch_summary(
    run_dir: Path,
    *,
    metrics: BacktestMetrics,
    artifacts: dict[str, Path],
    strategy_rows: dict[str, dict[str, Any]],
    long_short_rows: dict[str, dict[str, Any]],
    session_rows: list[dict[str, Any]],
    calendar: TradingCalendarProtocol,
    session_config: ReportingSessionConfig,
) -> None:
    path = run_dir / "summary.json"
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.update({
        "starting_equity": metrics.starting_equity,
        "ending_equity": metrics.ending_equity,
        "pnl": metrics.pnl,
        "fees_paid": metrics.fees_paid,
        "trade_count": metrics.trade_count,
        "win_count": metrics.win_count,
        "loss_count": metrics.loss_count,
        "winrate": metrics.winrate,
        "avg_win": metrics.avg_win,
        "avg_loss": metrics.avg_loss,
        "profit_factor": metrics.profit_factor,
        "max_drawdown": metrics.max_drawdown,
        "drawdown_pct": metrics.drawdown_pct,
        "avg_hold_seconds": metrics.avg_hold_seconds,
        "largest_win": metrics.largest_win,
        "largest_loss": metrics.largest_loss,
        "strategy_attribution": strategy_rows,
        "long_short_breakdown": long_short_rows,
        "sessions": {
            row["session_label"]: {
                key: value for key, value in row.items() if key != "session_label"
            }
            for row in session_rows
        },
        "reporting": {
            "session_bucket_basis": "entry_timestamp",
            "calendar": calendar.stats(),
            "session_timezone": session_config.timezone_name,
            "session_buckets": [
                {
                    "label": bucket.label,
                    "start_hour": bucket.start_hour,
                    "end_hour": bucket.end_hour,
                }
                for bucket in session_config.buckets
            ],
            "out_of_session_label": session_config.out_of_session_label,
        },
        "artifacts": {name: str(path) for name, path in artifacts.items()},
    })
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _nested_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _write_simple_equity_png(path: Path, values: list[float]) -> None:
    width = 960
    height = 320
    padding = 24
    pixels = bytearray([255] * (width * height * 3))
    _draw_rect(pixels, width, height, 0, 0, width - 1, height - 1, (235, 239, 245))
    _draw_rect(pixels, width, height, padding, padding, width - padding, height - padding, (255, 255, 255))
    if values:
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum or 1.0
        points: list[tuple[int, int]] = []
        usable_width = width - (padding * 2)
        usable_height = height - (padding * 2)
        for index, value in enumerate(values):
            x = padding + int(index * usable_width / max(1, len(values) - 1))
            y = padding + usable_height - int((value - minimum) * usable_height / span)
            points.append((x, y))
        for start, end in zip(points, points[1:]):
            _draw_line(pixels, width, height, start, end, (15, 23, 42))
    raw = bytearray()
    stride = width * 3
    for row in range(height):
        raw.append(0)
        start = row * stride
        raw.extend(pixels[start:start + stride])
    _write_png_bytes(path, width, height, bytes(raw))


def _draw_rect(
    pixels: bytearray,
    width: int,
    height: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int],
) -> None:
    for x in range(left, right + 1):
        _set_pixel(pixels, width, height, x, top, color)
        _set_pixel(pixels, width, height, x, bottom, color)
    for y in range(top, bottom + 1):
        _set_pixel(pixels, width, height, left, y, color)
        _set_pixel(pixels, width, height, right, y, color)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        _set_pixel(pixels, width, height, x0, y0, color)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * error
        if e2 >= dy:
            error += dy
            x0 += sx
        if e2 <= dx:
            error += dx
            y0 += sy


def _set_pixel(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    offset = (y * width + x) * 3
    pixels[offset:offset + 3] = bytes(color)


def _write_png_bytes(path: Path, width: int, height: int, raw_image_bytes: bytes) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = b"".join([
        b"\x89PNG\r\n\x1a\n",
        chunk(b"IHDR", ihdr),
        chunk(b"IDAT", zlib.compress(raw_image_bytes)),
        chunk(b"IEND", b""),
    ])
    path.write_bytes(payload)

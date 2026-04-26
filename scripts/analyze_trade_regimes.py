from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


MODEL_COLUMNS = [
    "event_ts",
    "reg_regime_label",
    "reg_confidence",
    "reg_transition_risk",
    "reg_no_trade_prob",
    "reg_trend_suitability",
    "reg_breakout_suitability",
    "reg_meanrev_suitability",
    "reg_reversal_suitability",
    "vol_sigma_effective",
    "vol_shock_score",
    "vol_jump_prob_1",
]


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    gross_pnl: float
    fees_paid: float
    net_pnl: float
    hold_seconds: int
    exit_reason: str | None


def _nested_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value:
            return value["value"]
        if "amount" in value:
            return value["amount"]
    return value


def _parse_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _parse_trade(row: dict[str, Any], ordinal: int) -> TradeRecord:
    if "realized_pnl" in row and "entry_timestamp" in row and "exit_timestamp" in row:
        gross_pnl = float(_nested_value(row["realized_pnl"]))
        fees_paid = float(_nested_value(row["fees_paid"]))
        return TradeRecord(
            trade_id=str(_nested_value(row["trade_id"])),
            strategy_id=str(_nested_value(row["strategy_id"])),
            symbol=str(_nested_value(row["symbol"])),
            side=str(row["side"]),
            entry_ts=_parse_timestamp(row["entry_timestamp"]),
            exit_ts=_parse_timestamp(row["exit_timestamp"]),
            gross_pnl=gross_pnl,
            fees_paid=fees_paid,
            net_pnl=gross_pnl - fees_paid,
            hold_seconds=int(row["hold_seconds"]),
            exit_reason=None if row.get("exit_reason") is None else str(row["exit_reason"]),
        )

    if "entry_time" in row and "exit_time" in row and "pnl" in row:
        entry_ts = _parse_timestamp(row["entry_time"])
        exit_ts = _parse_timestamp(row["exit_time"])
        gross_pnl = float(row["pnl"])
        fees_paid = float(_nested_value(row.get("fees_paid", 0.0)))
        strategy_id = str(
            row.get("strategy_id")
            or row.get("metadata", {}).get("strategy_id")
            or row.get("metadata", {}).get("meta", {}).get("strategy_id")
            or "UNKNOWN"
        )
        symbol = str(
            row.get("symbol")
            or row.get("metadata", {}).get("symbol")
            or "ETHUSDT"
        )
        hold_seconds = int(max(0.0, (exit_ts - entry_ts).total_seconds()))
        return TradeRecord(
            trade_id=str(row.get("trade_id") or f"{strategy_id}:{ordinal}"),
            strategy_id=strategy_id,
            symbol=symbol,
            side=str(row["side"]),
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            gross_pnl=gross_pnl,
            fees_paid=fees_paid,
            net_pnl=gross_pnl - fees_paid,
            hold_seconds=hold_seconds,
            exit_reason=None if row.get("reason") is None else str(row["reason"]),
        )

    raise ValueError(f"Unsupported trade schema with keys: {sorted(row.keys())}")


def _load_trades(path: Path) -> list[TradeRecord]:
    trades: list[TradeRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            trades.append(_parse_trade(json.loads(line), ordinal))
    return trades


def _load_model(path: Path) -> pd.DataFrame:
    table = pq.read_table(path, columns=MODEL_COLUMNS)
    df = table.to_pandas()
    df["ts"] = pd.to_datetime(df["event_ts"], unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def _row_snapshot(prefix: str, row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {
            f"{prefix}_regime": None,
            f"{prefix}_regime_ts": None,
            f"{prefix}_regime_confidence": None,
            f"{prefix}_transition_risk": None,
            f"{prefix}_no_trade_prob": None,
            f"{prefix}_trend_suitability": None,
            f"{prefix}_breakout_suitability": None,
            f"{prefix}_meanrev_suitability": None,
            f"{prefix}_reversal_suitability": None,
            f"{prefix}_vol_sigma_effective": None,
            f"{prefix}_vol_shock_score": None,
            f"{prefix}_vol_jump_prob_1": None,
        }
    return {
        f"{prefix}_regime": row["reg_regime_label"],
        f"{prefix}_regime_ts": row["ts"].isoformat(),
        f"{prefix}_regime_confidence": float(row["reg_confidence"]),
        f"{prefix}_transition_risk": float(row["reg_transition_risk"]),
        f"{prefix}_no_trade_prob": float(row["reg_no_trade_prob"]),
        f"{prefix}_trend_suitability": float(row["reg_trend_suitability"]),
        f"{prefix}_breakout_suitability": float(row["reg_breakout_suitability"]),
        f"{prefix}_meanrev_suitability": float(row["reg_meanrev_suitability"]),
        f"{prefix}_reversal_suitability": float(row["reg_reversal_suitability"]),
        f"{prefix}_vol_sigma_effective": float(row["vol_sigma_effective"]),
        f"{prefix}_vol_shock_score": float(row["vol_shock_score"]),
        f"{prefix}_vol_jump_prob_1": float(row["vol_jump_prob_1"]),
    }


def _dominant_regime(
    model: pd.DataFrame,
    ts_ms: np.ndarray,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
) -> dict[str, Any]:
    entry_ms = int(entry_ts.value // 1_000_000)
    exit_ms = int(exit_ts.value // 1_000_000)
    start_idx = int(np.searchsorted(ts_ms, entry_ms, side="right") - 1)
    end_idx = int(np.searchsorted(ts_ms, exit_ms, side="right") - 1)
    if start_idx < 0:
        return {
            "dominant_regime": None,
            "dominant_regime_share": None,
            "regime_path": None,
            "regime_points_in_trade": 0,
        }

    if end_idx < start_idx:
        end_idx = start_idx

    durations: dict[str, int] = defaultdict(int)
    regime_path: list[str] = []
    points = 0

    for idx in range(start_idx, min(end_idx + 1, len(model))):
        regime = str(model.at[idx, "reg_regime_label"])
        interval_start = entry_ms if idx == start_idx else int(ts_ms[idx])
        if idx + 1 < len(model):
            next_ns = int(ts_ms[idx + 1])
        else:
            next_ns = exit_ms
        interval_end = min(exit_ms, next_ns)
        duration = max(0, interval_end - interval_start)
        durations[regime] += duration
        points += 1
        if not regime_path or regime_path[-1] != regime:
            regime_path.append(regime)

    if not durations:
        regime = str(model.at[start_idx, "reg_regime_label"])
        return {
            "dominant_regime": regime,
            "dominant_regime_share": 1.0,
            "regime_path": regime,
            "regime_points_in_trade": 1,
        }

    dominant = max(durations.items(), key=lambda item: item[1])[0]
    total = sum(durations.values())
    share = float(durations[dominant]) / float(total) if total > 0 else 1.0
    return {
        "dominant_regime": dominant,
        "dominant_regime_share": share,
        "regime_path": " -> ".join(regime_path),
        "regime_points_in_trade": points,
    }


def _summarize(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["win"] = work["net_pnl"] > 0
    work["loss"] = work["net_pnl"] < 0
    grouped = (
        work.groupby(group_col, dropna=False)
        .agg(
            trade_count=("trade_id", "count"),
            gross_pnl=("gross_pnl", "sum"),
            fees_paid=("fees_paid", "sum"),
            net_pnl=("net_pnl", "sum"),
            avg_net_pnl=("net_pnl", "mean"),
            median_net_pnl=("net_pnl", "median"),
            avg_hold_hours=("hold_seconds", lambda s: float(np.mean(s) / 3600.0)),
            win_count=("win", "sum"),
            loss_count=("loss", "sum"),
            avg_entry_confidence=("entry_regime_confidence", "mean"),
            avg_entry_transition_risk=("entry_transition_risk", "mean"),
            avg_entry_no_trade_prob=("entry_no_trade_prob", "mean"),
            avg_entry_vol_sigma=("entry_vol_sigma_effective", "mean"),
            avg_entry_vol_shock=("entry_vol_shock_score", "mean"),
        )
        .reset_index()
    )
    grouped["win_rate_pct"] = np.where(
        grouped["trade_count"] > 0,
        grouped["win_count"] * 100.0 / grouped["trade_count"],
        0.0,
    )
    return grouped.sort_values("net_pnl", ascending=False).reset_index(drop=True)


def _transition_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["transition"] = (
        work["entry_regime"].fillna("NA").astype(str)
        + " -> "
        + work["exit_regime"].fillna("NA").astype(str)
    )
    return _summarize(work, "transition")


def analyze_run(run_dir: Path, model: pd.DataFrame) -> dict[str, Any]:
    trades_path = run_dir / "trades.jsonl"
    trades = _load_trades(trades_path)
    ts_ms = model["event_ts"].astype("int64").to_numpy()
    model_indexed = model.reset_index(drop=True)

    detail_rows: list[dict[str, Any]] = []
    for trade in trades:
        entry_idx = int(np.searchsorted(ts_ms, int(trade.entry_ts.value // 1_000_000), side="right") - 1)
        exit_idx = int(np.searchsorted(ts_ms, int(trade.exit_ts.value // 1_000_000), side="right") - 1)
        entry_row = model_indexed.iloc[entry_idx] if entry_idx >= 0 else None
        exit_row = model_indexed.iloc[exit_idx] if exit_idx >= 0 else None
        dominant = _dominant_regime(model_indexed, ts_ms, trade.entry_ts, trade.exit_ts)
        detail = {
            "trade_id": trade.trade_id,
            "strategy_id": trade.strategy_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_timestamp": trade.entry_ts.isoformat(),
            "exit_timestamp": trade.exit_ts.isoformat(),
            "hold_seconds": trade.hold_seconds,
            "hold_hours": trade.hold_seconds / 3600.0,
            "exit_reason": trade.exit_reason,
            "gross_pnl": trade.gross_pnl,
            "fees_paid": trade.fees_paid,
            "net_pnl": trade.net_pnl,
            "won_net": bool(trade.net_pnl > 0),
            "lost_net": bool(trade.net_pnl < 0),
        }
        detail.update(_row_snapshot("entry", entry_row))
        detail.update(_row_snapshot("exit", exit_row))
        detail.update(dominant)
        detail_rows.append(detail)

    details_df = pd.DataFrame(detail_rows)
    entry_summary = _summarize(details_df, "entry_regime")
    dominant_summary = _summarize(details_df, "dominant_regime")
    transition_summary = _transition_summary(details_df)

    output_dir = run_dir / f"regime_analysis_{Path(args.model_parquet).stem}"
    output_dir.mkdir(parents=True, exist_ok=True)
    details_path = output_dir / "trade_regime_details.csv"
    entry_path = output_dir / "entry_regime_summary.csv"
    dominant_path = output_dir / "dominant_regime_summary.csv"
    transition_path = output_dir / "entry_exit_transition_summary.csv"
    summary_path = output_dir / "summary.json"

    details_df.to_csv(details_path, index=False)
    entry_summary.to_csv(entry_path, index=False)
    dominant_summary.to_csv(dominant_path, index=False)
    transition_summary.to_csv(transition_path, index=False)

    summary = {
        "run_dir": str(run_dir),
        "trade_count": int(len(details_df)),
        "model_parquet": str(args.model_parquet),
        "detail_csv": str(details_path),
        "entry_regime_summary_csv": str(entry_path),
        "dominant_regime_summary_csv": str(dominant_path),
        "entry_exit_transition_summary_csv": str(transition_path),
        "top_entry_regimes_by_net_pnl": entry_summary.head(10).to_dict(orient="records"),
        "top_dominant_regimes_by_net_pnl": dominant_summary.head(10).to_dict(orient="records"),
        "top_transitions_by_net_pnl": transition_summary.head(10).to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze backtest trades by external regime parquet.")
    parser.add_argument("--model-parquet", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    return parser


def main() -> int:
    global args
    args = build_parser().parse_args()
    model = _load_model(args.model_parquet)
    results = [analyze_run(run_dir.resolve(), model) for run_dir in args.run_dir]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

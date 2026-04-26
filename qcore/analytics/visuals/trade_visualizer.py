from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import csv
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .chart_builder import ChartBuilder, TIMEFRAME_RULES
from .chart_plotter import ChartPlotter
from .chart_types import IndicatorSpec, IndicatorType, MarkType


TIMEFRAME_TO_DELTA = {
    "1m": pd.Timedelta(minutes=1),
    "3m": pd.Timedelta(minutes=3),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "30m": pd.Timedelta(minutes=30),
    "1h": pd.Timedelta(hours=1),
    "2h": pd.Timedelta(hours=2),
    "4h": pd.Timedelta(hours=4),
    "6h": pd.Timedelta(hours=6),
    "8h": pd.Timedelta(hours=8),
    "12h": pd.Timedelta(hours=12),
    "1d": pd.Timedelta(days=1),
}


def _default_indicators() -> list[IndicatorSpec]:
    return [
        IndicatorSpec(type=IndicatorType.EMA, period=20, color="#f59e0b"),
        IndicatorSpec(type=IndicatorType.EMA, period=50, color="#8b5cf6"),
        IndicatorSpec(type=IndicatorType.EMA, period=200, color="#0ea5e9"),
    ]


@dataclass(frozen=True, slots=True)
class ContextTimeframePanel:
    timeframe: str
    bars_before: int
    bars_after: int
    indicator_specs: tuple[IndicatorSpec, ...] = ()


@dataclass(slots=True)
class TradeVisualizerConfig:
    strategy_id: str | None = None
    max_trades: int | None = None
    output_dir_name: str = "visuals"
    chart_timeframe: str | None = None
    main_bars_before: int = 180
    main_bars_after: int = 180
    volume_panel: bool = True
    volatility_panel: bool = True
    delta_panel: bool = False
    show_legends: bool = False
    dpi: int = 170
    indicator_specs: list[IndicatorSpec] = field(default_factory=_default_indicators)
    context_panels: list[ContextTimeframePanel] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TradeRecord:
    trade_id: str
    strategy_id: str | None
    symbol: str
    venue: str | None
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_timestamp: datetime
    exit_timestamp: datetime
    realized_pnl: float
    fees_paid: float
    hold_seconds: int
    exit_reason: str | None


@dataclass(frozen=True, slots=True)
class EntryPlan:
    stop_loss: float | None
    take_profit: float | None
    trail_amount: float | None
    activation_amount: float | None
    max_hold_bars: int | None
    component_name: str | None
    signal_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VisualizationResult:
    run_dir: Path
    output_dir: Path
    chart_count: int
    index_csv: Path
    manifest_json: Path


class MonthlyParquetRangeLoader:
    def __init__(self, files: Iterable[str | Path]) -> None:
        self.files = tuple(Path(p) for p in files)
        self._month_to_file: dict[tuple[int, int], Path] = {}
        self._fallback_files: list[Path] = []
        self._cache: dict[Path, pd.DataFrame] = {}
        for path in self.files:
            try:
                year = int(path.parent.name)
                month = int(path.stem)
            except Exception:
                self._fallback_files.append(path)
                continue
            self._month_to_file[(year, month)] = path

    @staticmethod
    def _coerce_open_time(series: pd.Series) -> pd.Series:
        if pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series):
            return pd.to_datetime(series, unit="ms", utc=True, errors="raise")
        return pd.to_datetime(series, utc=True, errors="raise")

    def load_range(self, start: datetime, end: datetime) -> pd.DataFrame:
        months: list[tuple[int, int]] = []
        cursor = datetime(pd.Timestamp(start).year, pd.Timestamp(start).month, 1, tzinfo=UTC)
        end_cursor = datetime(pd.Timestamp(end).year, pd.Timestamp(end).month, 1, tzinfo=UTC)
        while cursor <= end_cursor:
            months.append((cursor.year, cursor.month))
            if cursor.month == 12:
                cursor = datetime(cursor.year + 1, 1, 1, tzinfo=UTC)
            else:
                cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=UTC)

        selected: list[Path] = []
        for year_month in months:
            path = self._month_to_file.get(year_month)
            if path is not None:
                selected.append(path)
        if not selected:
            selected = list(self._fallback_files or self.files)

        frames: list[pd.DataFrame] = []
        for path in selected:
            frame = self._cache.get(path)
            if frame is None:
                frame = pd.read_parquet(path)
                frame["open_time"] = self._coerce_open_time(frame["open_time"])
                frame = frame.sort_values("open_time").reset_index(drop=True)
                self._cache[path] = frame
            frames.append(frame)

        if not frames:
            raise ValueError("No parquet frames loaded for requested range.")
        out = pd.concat(frames, ignore_index=True)
        out = out[(out["open_time"] >= pd.Timestamp(start)) & (out["open_time"] <= pd.Timestamp(end))].copy()
        if out.empty:
            raise ValueError("Loaded source files but no rows remain for requested range.")
        return out.reset_index(drop=True)


def _serialize_indicator_spec(spec: IndicatorSpec) -> dict[str, Any]:
    return {
        "type": spec.type.value,
        "period": spec.period,
        "source": spec.source,
        "column_name": spec.column_name,
        "color": spec.color,
        "linewidth": spec.linewidth,
        "alpha": spec.alpha,
        "panel": spec.panel,
        "extra": dict(spec.extra),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _nested_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value and len(value) == 1:
            return value["value"]
        if "amount" in value and len(value) >= 1:
            return value["amount"]
    return value


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_trade(obj: dict[str, Any]) -> TradeRecord:
    return TradeRecord(
        trade_id=str(_nested_value(obj["trade_id"])),
        strategy_id=None if obj.get("strategy_id") is None else str(_nested_value(obj["strategy_id"])),
        symbol=str(_nested_value(obj["symbol"])),
        venue=None if obj.get("venue") is None else str(_nested_value(obj["venue"])),
        side=str(obj["side"]),
        quantity=float(_nested_value(obj["quantity"])),
        entry_price=float(_nested_value(obj["entry_price"])),
        exit_price=float(_nested_value(obj["exit_price"])),
        entry_timestamp=_parse_timestamp(obj["entry_timestamp"]),
        exit_timestamp=_parse_timestamp(obj["exit_timestamp"]),
        realized_pnl=float(_nested_value(obj["realized_pnl"])),
        fees_paid=float(_nested_value(obj["fees_paid"])),
        hold_seconds=int(obj["hold_seconds"]),
        exit_reason=None if obj.get("exit_reason") is None else str(obj["exit_reason"]),
    )


def _load_entry_plan_lookup(fills: list[dict[str, Any]]) -> dict[tuple[str | None, str, str, str, str], EntryPlan]:
    lookup: dict[tuple[str | None, str, str, str, str], EntryPlan] = {}
    for fill in fills:
        exit_policy = fill.get("exit_policy")
        if not exit_policy:
            continue
        strategy_id = None if fill.get("strategy_id") is None else str(_nested_value(fill["strategy_id"]))
        symbol = str(_nested_value(fill["symbol"]))
        timestamp = str(fill["timestamp"])
        quantity = str(_nested_value(fill["quantity"]))
        side = str(fill["side"])
        trailing = exit_policy.get("trailing_stop") or {}
        metadata = fill.get("metadata", {})
        signal_metadata = metadata.get("signal_metadata") or {}
        lookup[(strategy_id, symbol, timestamp, side, quantity)] = EntryPlan(
            stop_loss=None if exit_policy.get("stop_loss") is None else float(_nested_value(exit_policy["stop_loss"])),
            take_profit=None if exit_policy.get("take_profit") is None else float(_nested_value(exit_policy["take_profit"])),
            trail_amount=None if trailing.get("trail_amount") is None else float(trailing["trail_amount"]),
            activation_amount=None if trailing.get("activation_amount") is None else float(trailing["activation_amount"]),
            max_hold_bars=exit_policy.get("max_hold_bars"),
            component_name=(exit_policy.get("metadata") or {}).get("component_name"),
            signal_metadata=signal_metadata,
        )
    return lookup


def _entry_fill_side(trade_side: str) -> str:
    return "BUY" if trade_side.upper() == "LONG" else "SELL"


def _trade_slug(trade: TradeRecord) -> str:
    ts = trade.entry_timestamp.strftime("%Y%m%d_%H%M%S")
    side = trade.side.lower()
    return f"{trade.trade_id}_{trade.symbol}_{side}_{ts}"


def _metrics_lines(trade: TradeRecord, plan: EntryPlan | None) -> list[str]:
    lines = [
        f"trade_id     : {trade.trade_id}",
        f"strategy     : {trade.strategy_id or '-'}",
        f"symbol       : {trade.symbol}",
        f"side         : {trade.side}",
        f"entry / exit : {trade.entry_timestamp.isoformat()} -> {trade.exit_timestamp.isoformat()}",
        f"entry_px     : {trade.entry_price:.6f}",
        f"exit_px      : {trade.exit_price:.6f}",
        f"pnl / fees   : {trade.realized_pnl:.4f} / {trade.fees_paid:.4f}",
        f"hold_seconds : {trade.hold_seconds}",
        f"exit_reason  : {trade.exit_reason or '-'}",
    ]
    if plan is not None:
        lines.append(f"component    : {plan.component_name or '-'}")
        lines.append(f"stop / tp    : {plan.stop_loss if plan.stop_loss is not None else '-'} / {plan.take_profit if plan.take_profit is not None else '-'}")
        if plan.trail_amount is not None:
            lines.append(f"trail / act  : {plan.trail_amount:.6f} / {plan.activation_amount if plan.activation_amount is not None else '-'}")
    return lines


def _annotate_trade(builder: ChartBuilder, trade: TradeRecord, plan: EntryPlan | None, *, entry_label: str = "E", exit_label: str = "X") -> None:
    hold_color = "#dbeafe" if trade.side.upper() == "LONG" else "#fee2e2"
    entry_color = "#2563eb" if trade.side.upper() == "LONG" else "#7c3aed"
    exit_color = "#16a34a" if trade.realized_pnl >= 0 else "#dc2626"

    frame_low = float(builder.df["low"].min())
    frame_high = float(builder.df["high"].max())
    frame_range = max(frame_high - frame_low, trade.entry_price * 0.01, 1e-9)
    frame_padding = max(frame_range * 0.75, trade.entry_price * 0.015)
    visible_min = frame_low - frame_padding
    visible_max = frame_high + frame_padding

    def _visible_level(level: float | None) -> bool:
        if level is None:
            return False
        return visible_min <= float(level) <= visible_max

    builder.add_range(trade.entry_timestamp, trade.exit_timestamp, text=None, color=hold_color, alpha=0.16)
    builder.add_mark(trade.entry_timestamp, mark_type=MarkType.BAR_LABEL, text=entry_label, color=entry_color, containing=True, alpha=0.96)
    builder.add_mark(trade.entry_timestamp, mark_type=MarkType.VLINE, color=entry_color, containing=True, alpha=0.85)
    builder.add_mark(trade.exit_timestamp, mark_type=MarkType.BAR_LABEL, text=exit_label, color=exit_color, containing=True, alpha=0.96)
    builder.add_mark(trade.exit_timestamp, mark_type=MarkType.VLINE, color=exit_color, containing=True, alpha=0.85)

    builder.add_hline(trade.entry_price, text="Entry", color="#111827", alpha=0.9, linestyle="-", linewidth=1.0)
    if plan is not None and _visible_level(plan.stop_loss):
        builder.add_hline(plan.stop_loss, text="Stop", color="#dc2626", alpha=0.92, linestyle="--", linewidth=1.0)
    if plan is not None and _visible_level(plan.take_profit):
        builder.add_hline(plan.take_profit, text="TP", color="#16a34a", alpha=0.92, linestyle="--", linewidth=1.0)


def _set_axis_time_labels(ax, frame: pd.DataFrame, *, fontsize: int = 8) -> None:
    positions = ChartPlotter.tick_positions(len(frame))
    labels = [frame.iloc[pos]["open_time"].strftime("%m-%d %H:%M") for pos in positions]
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=fontsize)


def _plot_metrics_panel(*, ax, rows: list[str]) -> None:
    ax.set_axis_off()
    if not rows:
        return
    ax.text(
        0.015,
        0.90,
        "\n".join(rows),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9.5,
        family="monospace",
        color="#111827",
        bbox={"boxstyle": "round,pad=0.40", "facecolor": "white", "edgecolor": "#9ca3af", "linewidth": 0.9, "alpha": 0.88},
        zorder=9,
    )


def _plot_price_axis(ax, builder: ChartBuilder, *, show_legends: bool) -> pd.DataFrame:
    frame = ChartPlotter._prepare_frame(df=builder.df, time_col="open_time")
    zero_price = float(frame["close"].iloc[0])
    frame = ChartPlotter._build_indicator_frame(
        frame=frame,
        zero_price=zero_price,
        volatility_window=20,
        volume_window=20,
        volume_spike_ratio=1.8,
        delta_smooth_window=5,
    )
    ChartPlotter._plot_price_background_annotations(ax, frame)
    if builder.chart_objects:
        ChartPlotter._plot_chart_objects(ax, frame, builder.chart_objects)
    ChartPlotter._plot_candles(ax, frame)
    ChartPlotter._plot_indicator_overlays(ax, frame, builder.indicator_specs)
    ChartPlotter._add_price_headroom(ax)
    ChartPlotter._plot_bar_annotations(ax, frame)
    ChartPlotter._plot_range_annotations(ax, frame)
    ax.set_ylabel(str(builder.tf))
    ax.grid(axis="y", alpha=0.16)
    if show_legends:
        ChartPlotter._legend_if_needed(ax, loc="upper left", fontsize=8, ncol=3)
    return frame


def _plot_trade_chart(
    *,
    main_builder: ChartBuilder,
    context_builders: list[tuple[str, ChartBuilder]],
    trade: TradeRecord,
    plan: EntryPlan | None,
    config: TradeVisualizerConfig,
    savepath: Path,
) -> None:
    import matplotlib.pyplot as plt

    panels = ["price", "metrics", *[f"context_{tf}" for tf, _ in context_builders]]
    if config.volatility_panel:
        panels.append("volatility")
    if config.volume_panel:
        panels.append("volume")
    if config.delta_panel:
        panels.append("delta")

    height_ratios: list[float] = []
    for panel in panels:
        if panel == "price":
            height_ratios.append(4.5)
        elif panel == "metrics":
            height_ratios.append(0.9)
        elif panel.startswith("context_"):
            height_ratios.append(2.3)
        elif panel == "volatility":
            height_ratios.append(1.3)
        elif panel == "volume":
            height_ratios.append(1.4)
        else:
            height_ratios.append(1.3)

    fig, axes = plt.subplots(
        len(panels),
        1,
        figsize=(16, max(8, 3 * len(panels))),
        constrained_layout=False,
        gridspec_kw={"height_ratios": height_ratios, "hspace": 0.08},
    )
    axes_list = [axes] if len(panels) == 1 else list(axes)
    ax_map = {name: ax for name, ax in zip(panels, axes_list)}

    main_frame = _plot_price_axis(ax_map["price"], main_builder, show_legends=config.show_legends)
    _plot_metrics_panel(ax=ax_map["metrics"], rows=_metrics_lines(trade, plan))

    for timeframe, builder in context_builders:
        frame = _plot_price_axis(ax_map[f"context_{timeframe}"], builder, show_legends=False)
        ax_map[f"context_{timeframe}"].set_title(f"Context {timeframe}", loc="left", fontsize=10)
        _set_axis_time_labels(ax_map[f"context_{timeframe}"], frame)

    if config.volatility_panel:
        ChartPlotter._plot_volatility_panel(ax=ax_map["volatility"], frame=main_frame, volatility_window=20)
        ax_map["volatility"].set_ylabel("Vol %")
        ax_map["volatility"].grid(axis="y", alpha=0.16)
        _set_axis_time_labels(ax_map["volatility"], main_frame)

    if config.volume_panel:
        ChartPlotter._plot_volume_panel(ax=ax_map["volume"], frame=main_frame, volume_window=20, volume_spike_ratio=1.8)
        ax_map["volume"].set_ylabel("Volume")
        ax_map["volume"].grid(axis="y", alpha=0.16)
        _set_axis_time_labels(ax_map["volume"], main_frame)

    if config.delta_panel:
        ChartPlotter._plot_delta_panel(ax=ax_map["delta"], frame=main_frame)
        ax_map["delta"].set_ylabel("Diff %/bar")
        ax_map["delta"].grid(axis="y", alpha=0.16)
        _set_axis_time_labels(ax_map["delta"], main_frame)

    title = f"{trade.symbol} | {trade.strategy_id or '-'} | {trade.trade_id} | {trade.side} | pnl={trade.realized_pnl:.2f} | reason={trade.exit_reason or '-'}"
    ax_map["price"].set_title(title)
    _set_axis_time_labels(ax_map["price"], main_frame)

    savepath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(savepath, dpi=config.dpi)
    plt.close(fig)


def _discover_data_files(manifest: dict[str, Any]) -> tuple[Path, ...]:
    files = manifest.get("metadata", {}).get("resolved_data_files") or []
    if files:
        return tuple(Path(p) for p in files)
    data_path = manifest.get("data_path")
    if not data_path:
        return ()
    path = Path(str(data_path))
    if path.is_file():
        return (path,)
    return tuple(sorted(path.rglob("*.parquet")))


def _source_timeframe(manifest: dict[str, Any]) -> str:
    return str(
        manifest.get("metadata", {}).get("execution", {}).get("source_timeframe")
        or manifest.get("metadata", {}).get("source_descriptor", {}).get("source_timeframe")
        or "1m"
    )


def visualize_run_trades(run_dir: str | Path, config: TradeVisualizerConfig | None = None) -> VisualizationResult:
    run_path = Path(run_dir)
    config = config or TradeVisualizerConfig()
    if config.context_panels:
        raise ValueError("Context timeframe panes are not enabled yet in this QuantOS visualizer pass.")

    manifest = _read_json(run_path / "manifest.json")
    trades = [_parse_trade(row) for row in _read_jsonl(run_path / "trades.jsonl")]
    fills = _read_jsonl(run_path / "fills.jsonl")
    if config.strategy_id:
        trades = [trade for trade in trades if trade.strategy_id == config.strategy_id]
    if config.max_trades is not None:
        trades = trades[: config.max_trades]

    files = _discover_data_files(manifest)
    if not files:
        raise ValueError("No source parquet files could be discovered from the run manifest.")
    loader = MonthlyParquetRangeLoader(files)
    source_tf = _source_timeframe(manifest)
    source_delta = TIMEFRAME_TO_DELTA.get(source_tf)
    if source_delta is None:
        raise ValueError(f"Unsupported source timeframe for visualization: {source_tf}")
    chart_tf = config.chart_timeframe or source_tf
    chart_delta = TIMEFRAME_TO_DELTA.get(chart_tf)
    if chart_delta is None or chart_tf not in TIMEFRAME_RULES:
        raise ValueError(f"Unsupported chart timeframe for visualization: {chart_tf}")

    plan_lookup = _load_entry_plan_lookup(fills)
    output_dir = run_path / config.output_dir_name / "trades"
    output_dir.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict[str, Any]] = []

    for trade in trades:
        entry_fill_key = (
            trade.strategy_id,
            trade.symbol,
            trade.entry_timestamp.isoformat(),
            _entry_fill_side(trade.side),
            f"{trade.quantity:.4f}",
        )
        plan = plan_lookup.get(entry_fill_key)

        start = trade.entry_timestamp - (config.main_bars_before * chart_delta)
        end = trade.exit_timestamp + (config.main_bars_after * chart_delta)
        for panel in config.context_panels:
            delta = TIMEFRAME_TO_DELTA.get(panel.timeframe)
            if delta is None:
                continue
            start = min(start, trade.entry_timestamp - (panel.bars_before * delta))
            end = max(end, trade.exit_timestamp + (panel.bars_after * delta))

        df_base = loader.load_range(start=start, end=end)
        main_builder = ChartBuilder.from_dataframe(
            df_base=df_base,
            pair=trade.symbol,
            base_tf=source_tf,
            tf=chart_tf,
            start=start,
            end=end,
            indicator_specs=config.indicator_specs,
        )
        left = max(0, main_builder.resolve_containing_bar(trade.entry_timestamp) - config.main_bars_before)
        right = min(len(main_builder.df) - 1, main_builder.resolve_containing_bar(trade.exit_timestamp) + config.main_bars_after)
        main_builder.crop_by_range(left, right)
        _annotate_trade(main_builder, trade, plan)

        context_builders: list[tuple[str, ChartBuilder]] = []
        for panel in config.context_panels:
            if panel.timeframe == source_tf or panel.timeframe not in TIMEFRAME_RULES:
                continue
            builder = ChartBuilder.from_dataframe(
                df_base=df_base,
                pair=trade.symbol,
                base_tf=source_tf,
                tf=panel.timeframe,
                start=start,
                end=end,
                indicator_specs=list(panel.indicator_specs) if panel.indicator_specs else [],
            )
            left = max(0, builder.resolve_containing_bar(trade.entry_timestamp) - panel.bars_before)
            right = min(len(builder.df) - 1, builder.resolve_containing_bar(trade.exit_timestamp) + panel.bars_after)
            builder.crop_by_range(left, right)
            _annotate_trade(builder, trade, plan)
            context_builders.append((panel.timeframe, builder))

        chart_name = f"{_trade_slug(trade)}.png"
        savepath = output_dir / chart_name
        _plot_trade_chart(
            main_builder=main_builder,
            context_builders=context_builders,
            trade=trade,
            plan=plan,
            config=config,
            savepath=savepath,
        )

        index_rows.append(
            {
                "trade_id": trade.trade_id,
                "strategy_id": trade.strategy_id or "",
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_timestamp": trade.entry_timestamp.isoformat(),
                "exit_timestamp": trade.exit_timestamp.isoformat(),
                "realized_pnl": trade.realized_pnl,
                "fees_paid": trade.fees_paid,
                "exit_reason": trade.exit_reason or "",
                "component_name": "" if plan is None or plan.component_name is None else plan.component_name,
                "chart_path": str(savepath),
            }
        )

    index_csv = run_path / config.output_dir_name / "trade_charts_index.csv"
    with index_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(index_rows[0].keys()) if index_rows else ["trade_id", "chart_path"])
        writer.writeheader()
        if index_rows:
            writer.writerows(index_rows)

    manifest_json = run_path / config.output_dir_name / "manifest.json"
    manifest_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "run_dir": str(run_path),
                "chart_count": len(index_rows),
                "config": {
                    "strategy_id": config.strategy_id,
                    "max_trades": config.max_trades,
                    "output_dir_name": config.output_dir_name,
                    "chart_timeframe": config.chart_timeframe,
                    "main_bars_before": config.main_bars_before,
                    "main_bars_after": config.main_bars_after,
                    "volume_panel": config.volume_panel,
                    "volatility_panel": config.volatility_panel,
                    "delta_panel": config.delta_panel,
                    "show_legends": config.show_legends,
                    "dpi": config.dpi,
                    "indicator_specs": [_serialize_indicator_spec(spec) for spec in config.indicator_specs],
                    "context_panels": [
                        {
                            "timeframe": panel.timeframe,
                            "bars_before": panel.bars_before,
                            "bars_after": panel.bars_after,
                            "indicator_specs": [_serialize_indicator_spec(spec) for spec in panel.indicator_specs],
                        }
                        for panel in config.context_panels
                    ],
                },
                "index_csv": str(index_csv),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return VisualizationResult(
        run_dir=run_path,
        output_dir=run_path / config.output_dir_name,
        chart_count=len(index_rows),
        index_csv=index_csv,
        manifest_json=manifest_json,
    )

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qcore.analytics.visuals import ContextTimeframePanel, TradeVisualizerConfig, visualize_run_trades
from qcore.analytics.visuals.chart_types import IndicatorSpec, IndicatorType


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render post-backtest trade charts for a QuantOS run.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Path to a QuantOS run directory.")
    parser.add_argument("--strategy-id", type=str, default=None, help="Optional strategy_id filter.")
    parser.add_argument("--max-trades", type=int, default=None, help="Optional limit on number of trades to render.")
    parser.add_argument("--output-dir-name", type=str, default="visuals", help="Nested output folder inside the run directory.")
    parser.add_argument("--chart-timeframe", type=str, default=None, help="Chart timeframe, for example 1m, 5m, 1h.")
    parser.add_argument("--main-bars-before", type=int, default=180, help="Chart-timeframe bars before entry.")
    parser.add_argument("--main-bars-after", type=int, default=180, help="Chart-timeframe bars after exit.")
    parser.add_argument("--no-volume-panel", action="store_true", help="Disable volume panel.")
    parser.add_argument("--no-volatility-panel", action="store_true", help="Disable volatility panel.")
    parser.add_argument("--delta-panel", action="store_true", help="Enable delta-diff panel.")
    parser.add_argument("--show-legends", action="store_true", help="Show plot legends.")
    parser.add_argument("--ema-stack", nargs="*", type=int, default=None, help="EMA periods to overlay on the main chart.")
    parser.add_argument("--context-timeframes", nargs="*", default=[], help="Optional context timeframe panes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    indicator_specs = None
    if args.ema_stack:
        default_colors = ["#f59e0b", "#8b5cf6", "#14b8a6", "#0ea5e9", "#ef4444", "#22c55e"]
        indicator_specs = [
            IndicatorSpec(
                type=IndicatorType.EMA,
                period=int(period),
                color=default_colors[idx % len(default_colors)],
            )
            for idx, period in enumerate(args.ema_stack)
        ]
    context_panels = [ContextTimeframePanel(timeframe=tf, bars_before=80 if tf == "5m" else 48 if tf == "1h" else 24, bars_after=80 if tf == "5m" else 48 if tf == "1h" else 24) for tf in args.context_timeframes]
    config = TradeVisualizerConfig(
        strategy_id=args.strategy_id,
        max_trades=args.max_trades,
        output_dir_name=args.output_dir_name,
        chart_timeframe=args.chart_timeframe,
        main_bars_before=args.main_bars_before,
        main_bars_after=args.main_bars_after,
        volume_panel=not args.no_volume_panel,
        volatility_panel=not args.no_volatility_panel,
        delta_panel=args.delta_panel,
        show_legends=args.show_legends,
        indicator_specs=indicator_specs if indicator_specs is not None else TradeVisualizerConfig().indicator_specs,
        context_panels=context_panels,
    )
    result = visualize_run_trades(args.run_dir, config=config)
    print(
        json.dumps(
            {
                "run_dir": str(result.run_dir),
                "output_dir": str(result.output_dir),
                "chart_count": result.chart_count,
                "index_csv": str(result.index_csv),
                "manifest_json": str(result.manifest_json),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

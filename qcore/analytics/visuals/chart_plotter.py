from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from matplotlib import transforms as mtransforms
from matplotlib.patches import Rectangle

from .chart_types import ChartObjectType, IndicatorSpec, IndicatorType, MarkType


class ChartPlotter:
    CANDLE_UP = "#16a34a"
    CANDLE_DOWN = "#dc2626"

    ZERO_LINE = "#2563eb"
    CURRENT_LINE = "#6b7280"

    VOL_LOCAL = "#2563eb"
    VOL_BASELINE = "#93c5fd"
    VOL_ATR = "#f59e0b"

    VOLUME_BAR = "#94a3b8"
    VOLUME_SPIKE = "#f59e0b"
    VOLUME_AVG = "#1d4ed8"
    VOLUME_SPIKE_LINE = "#ef4444"

    DELTA_SMOOTH = "#7c3aed"
    DELTA_ZERO = "#374151"
    DELTA_POS = "#16a34a"
    DELTA_NEG = "#dc2626"

    DEFAULT_INDICATOR_COLORS = {
        IndicatorType.EMA.value: "#0ea5e9",
        IndicatorType.SMA.value: "#8b5cf6",
        IndicatorType.ATR.value: "#f59e0b",
        IndicatorType.VWAP.value: "#14b8a6",
    }

    @classmethod
    def plot(
        cls,
        df: pd.DataFrame,
        *,
        show: bool = False,
        savepath: str | Path | None = None,
        limit: int | None = None,
        title: str | None = None,
        symbol: str | None = None,
        time_col: str = "open_time",
        volume_panel: bool = True,
        volatility_panel: bool = True,
        delta_panel: bool = True,
        zero_line: bool = False,
        current_line: bool = False,
        zero_price: float | None = None,
        current_price: float | None = None,
        volatility_window: int = 20,
        volume_window: int = 20,
        volume_spike_ratio: float = 1.8,
        delta_smooth_window: int = 5,
        figsize: tuple[int, int] | None = None,
        dpi: int = 170,
        return_frame: bool = False,
        indicator_specs: list[IndicatorSpec] | None = None,
        chart_objects: list[dict] | None = None,
        show_legends: bool = False,
    ):
        frame = cls._prepare_frame(df=df, time_col=time_col)
        if frame.empty:
            raise ValueError("Input dataframe is empty after preparation.")

        if zero_price is None:
            zero_price = float(frame["close"].iloc[0])
        if current_price is None:
            current_price = float(frame["close"].iloc[-1])

        frame = cls._build_indicator_frame(
            frame=frame,
            zero_price=zero_price,
            volatility_window=volatility_window,
            volume_window=volume_window,
            volume_spike_ratio=volume_spike_ratio,
            delta_smooth_window=delta_smooth_window,
        )

        if limit is not None and limit > 0:
            frame = frame.tail(limit).reset_index(drop=True)

        panels = ["price"]
        if volatility_panel:
            panels.append("volatility")
        if volume_panel:
            panels.append("volume")
        if delta_panel:
            panels.append("delta")

        height_ratios: list[float] = []
        for panel in panels:
            if panel == "price":
                height_ratios.append(4.5)
            elif panel == "volatility":
                height_ratios.append(1.3)
            elif panel == "volume":
                height_ratios.append(1.5)
            else:
                height_ratios.append(1.4)

        if figsize is None:
            figsize = {1: (16, 7), 2: (16, 9), 3: (16, 11), 4: (16, 12)}[len(panels)]

        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(
            len(panels),
            1,
            figsize=figsize,
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": height_ratios, "hspace": 0.06},
        )

        axes_list = [axes] if len(panels) == 1 else list(axes)
        ax_map = {name: ax for name, ax in zip(panels, axes_list)}

        cls._plot_price_background_annotations(ax_map["price"], frame)
        if chart_objects:
            cls._plot_chart_objects(ax_map["price"], frame, chart_objects)
        cls._plot_candles(ax_map["price"], frame)
        cls._plot_indicator_overlays(ax_map["price"], frame, indicator_specs or [])

        if zero_line and zero_price is not None:
            ax_map["price"].axhline(float(zero_price), color=cls.ZERO_LINE, linestyle="--", linewidth=1.1)
        if current_line and current_price is not None:
            ax_map["price"].axhline(float(current_price), color=cls.CURRENT_LINE, linestyle=":", linewidth=1.0)

        cls._add_price_headroom(ax_map["price"])
        cls._plot_bar_annotations(ax_map["price"], frame)
        cls._plot_range_annotations(ax_map["price"], frame)
        ax_map["price"].set_ylabel("Price")
        ax_map["price"].grid(axis="y", alpha=0.18)

        if show_legends:
            cls._legend_if_needed(ax_map["price"], loc="upper left", fontsize=8, ncol=3)

        if volatility_panel:
            cls._plot_volatility_panel(ax=ax_map["volatility"], frame=frame, volatility_window=volatility_window)
            ax_map["volatility"].set_ylabel("Vol %")
            ax_map["volatility"].grid(axis="y", alpha=0.16)

        if volume_panel:
            cls._plot_volume_panel(
                ax=ax_map["volume"],
                frame=frame,
                volume_window=volume_window,
                volume_spike_ratio=volume_spike_ratio,
            )
            ax_map["volume"].set_ylabel("Volume")
            ax_map["volume"].grid(axis="y", alpha=0.16)

        if delta_panel:
            cls._plot_delta_panel(ax=ax_map["delta"], frame=frame)
            ax_map["delta"].set_ylabel("Diff %/bar")
            ax_map["delta"].grid(axis="y", alpha=0.16)

        ax_map["price"].set_title(title or cls._build_title(frame=frame, symbol=symbol, zero_price=zero_price))

        positions = cls.tick_positions(len(frame))
        labels = [frame.iloc[pos]["open_time"].strftime("%m-%d %H:%M") for pos in positions]
        axes_list[-1].set_xticks(positions)
        axes_list[-1].set_xticklabels(labels, rotation=35, ha="right")
        fig.canvas.draw()

        if savepath is not None:
            target = Path(savepath)
            target.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(target, dpi=dpi)

        if show:
            plt.show()
        else:
            plt.close(fig)

        if return_frame:
            return fig, axes_list, frame
        return fig, axes_list

    @classmethod
    def _prepare_frame(cls, *, df: pd.DataFrame, time_col: str) -> pd.DataFrame:
        frame = df.copy()
        required = {"open", "high", "low", "close"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        if time_col not in frame.columns:
            raise ValueError(f"Time column {time_col!r} not found in dataframe")

        frame[time_col] = pd.to_datetime(frame[time_col], utc=True, errors="raise")
        frame = frame.sort_values(time_col).reset_index(drop=True)
        frame = frame.rename(columns={time_col: "open_time"})

        numeric_cols = ["open", "high", "low", "close"]
        if "volume" in frame.columns:
            numeric_cols.append("volume")
        for col in numeric_cols:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        return frame

    @classmethod
    def _build_indicator_frame(
        cls,
        *,
        frame: pd.DataFrame,
        zero_price: float,
        volatility_window: int,
        volume_window: int,
        volume_spike_ratio: float,
        delta_smooth_window: int,
    ) -> pd.DataFrame:
        out = frame.copy().reset_index(drop=True)
        previous_close = out["close"].shift(1)
        true_range = pd.concat(
            [
                out["high"] - out["low"],
                (out["high"] - previous_close).abs(),
                (out["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        close_base = out["close"].where(out["close"] != 0)
        return_pct = out["close"].pct_change().fillna(0) * 100.0
        min_periods = max(2, min(5, volatility_window))

        out["close_return_pct"] = return_pct
        out["local_volatility"] = return_pct.rolling(volatility_window, min_periods=min_periods).std().fillna(0)
        out["local_volatility_baseline"] = out["local_volatility"].rolling(volatility_window, min_periods=1).mean()
        out["atr"] = true_range.rolling(14, min_periods=1).mean()
        out["atr_pct"] = ((out["atr"] / close_base) * 100.0).fillna(0)
        out["volume_avg"] = out["volume"].rolling(volume_window, min_periods=1).mean()
        out["volume_ratio"] = (out["volume"] / out["volume_avg"].where(out["volume_avg"] != 0)).fillna(0)
        out["is_volume_spike"] = out["volume_ratio"] >= volume_spike_ratio
        out["diff_pct"] = ((out["close"] / zero_price) - 1.0) * 100.0
        out["diff_velocity"] = out["diff_pct"].diff().fillna(0)
        out["diff_velocity_smooth"] = out["diff_velocity"].rolling(delta_smooth_window, min_periods=1).mean()
        return out

    @classmethod
    def _plot_candles(cls, ax, frame: pd.DataFrame) -> None:
        candle_width = 0.62
        for index, candle in frame.iterrows():
            rising = float(candle["close"]) >= float(candle["open"])
            color = cls.CANDLE_UP if rising else cls.CANDLE_DOWN
            ax.vlines(index, float(candle["low"]), float(candle["high"]), color=color, linewidth=0.8)
            body_bottom = min(float(candle["open"]), float(candle["close"]))
            body_height = abs(float(candle["close"] - candle["open"]))
            if body_height == 0:
                ax.hlines(float(candle["open"]), index - candle_width / 2, index + candle_width / 2, color=color, linewidth=1.0)
                continue
            body = Rectangle((index - candle_width / 2, body_bottom), candle_width, body_height, facecolor=color, edgecolor=color, linewidth=0.8)
            ax.add_patch(body)

    @classmethod
    def _plot_indicator_overlays(cls, ax, frame: pd.DataFrame, indicator_specs: Iterable[IndicatorSpec]) -> None:
        for spec in indicator_specs:
            if spec.panel != "price":
                continue
            col = spec.resolved_name()
            if col not in frame.columns:
                continue
            color = spec.color or cls.DEFAULT_INDICATOR_COLORS.get(spec.type.value, None)
            ax.plot(frame.index, frame[col], linewidth=spec.linewidth, alpha=spec.alpha, color=color, label=col.upper())

    @classmethod
    def _plot_price_background_annotations(cls, ax, frame: pd.DataFrame) -> None:
        for run in cls._collect_background_runs(frame):
            ax.axvspan(run["start_idx"], run["end_idx"], color=run["color"], alpha=run["alpha"])

    @classmethod
    def _iter_bar_annotations(cls, frame: pd.DataFrame):
        if "plot_ann" not in frame.columns:
            return
        for idx, ann_value in frame["plot_ann"].items():
            if not ann_value:
                continue
            anns = ann_value if isinstance(ann_value, list) else [ann_value]
            yield int(idx), anns

    @classmethod
    def _plot_bar_annotations(cls, ax, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        price_range = float(frame["high"].max() - frame["low"].min())
        y_offset = price_range * 0.02 if price_range > 0 else max(float(frame["close"].iloc[-1]) * 0.005, 1e-12)
        local_window = max(4, min(18, len(frame) // 120))
        x_spacing = max(4, min(12, len(frame) // 180))
        base_gap = max(y_offset * 2.0, price_range * 0.03 if price_range > 0 else y_offset * 4.0)
        stack_gap = max(base_gap * 0.85, price_range * 0.022 if price_range > 0 else y_offset * 2.5)
        planned_labels: list[dict] = []
        placed_labels: list[tuple[int, float]] = []
        required_top = None

        for idx, anns in cls._iter_bar_annotations(frame):
            row = frame.iloc[idx]
            for ann in anns:
                ann_type = ann.get("type")
                color = ann.get("color", "#2563eb")
                text = ann.get("text")
                if ann_type == MarkType.VLINE.value:
                    ax.axvline(idx, color=color, linestyle="--", linewidth=0.9, alpha=float(ann.get("alpha", 0.85)))
                if ann_type not in {MarkType.VLINE.value, MarkType.BAR_LABEL.value} or not text:
                    continue

                left = max(0, idx - local_window)
                right = min(len(frame), idx + local_window + 1)
                local_high = float(frame.iloc[left:right]["high"].max())
                anchor_y = float(row["high"]) + (y_offset * 0.15)
                label_y = max(local_high + base_gap, anchor_y + (base_gap * 0.75))
                label_y = cls._resolve_bar_label_y(idx=idx, proposed_y=label_y, placed_labels=placed_labels, x_spacing=x_spacing, min_y_gap=stack_gap)
                placed_labels.append((idx, label_y))
                planned_labels.append({"x": idx, "anchor_y": anchor_y, "label_y": label_y, "text": text, "color": color})
                needed_top = label_y + (base_gap * 0.65)
                required_top = needed_top if required_top is None else max(required_top, needed_top)

        if planned_labels:
            ymin, ymax = ax.get_ylim()
            if required_top is not None and required_top > ymax:
                ax.set_ylim(ymin, required_top)
            for label in planned_labels:
                cls._draw_bar_label(ax=ax, x=label["x"], anchor_y=label["anchor_y"], label_y=label["label_y"], text=label["text"], color=label["color"])

    @classmethod
    def _plot_range_annotations(cls, ax, frame: pd.DataFrame) -> None:
        for run in cls._collect_background_runs(frame):
            text = run["text"]
            if not text:
                continue
            mid_x = (run["start_idx"] + run["end_idx"]) / 2
            ax.annotate(
                text,
                xy=(mid_x, 1.0),
                xycoords=mtransforms.blended_transform_factory(ax.transData, ax.transAxes),
                xytext=(0, -10),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=8,
                fontweight="semibold",
                color=run["text_color"],
                bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.68},
                annotation_clip=False,
                zorder=5,
            )

    @classmethod
    def _collect_background_runs(cls, frame: pd.DataFrame) -> list[dict]:
        runs: list[dict] = []
        active: dict[tuple[str | None, str, float], dict] = {}
        for idx, anns in cls._iter_bar_annotations(frame):
            bg_keys_this_idx: set[tuple[str | None, str, float]] = set()
            for ann in anns:
                if ann.get("type") != MarkType.BG.value:
                    continue
                text = ann.get("text")
                color = ann.get("color", "#dcfce7")
                alpha = float(ann.get("alpha", 0.22))
                key = (text, color, alpha)
                bg_keys_this_idx.add(key)
                if key in active and active[key]["end_idx"] == idx - 0.5:
                    active[key]["end_idx"] = idx
                    continue
                run = {"start_idx": idx - 0.5, "end_idx": idx + 0.5, "text": text, "color": color, "alpha": alpha, "text_color": ann.get("text_color", "#0f172a")}
                active[key] = run
                runs.append(run)
            stale_keys = [key for key, run in active.items() if key not in bg_keys_this_idx and run["end_idx"] < idx - 0.5]
            for key in stale_keys:
                active.pop(key, None)
            for key in bg_keys_this_idx:
                if key in active:
                    active[key]["end_idx"] = idx + 0.5
        return runs

    @classmethod
    def _plot_chart_objects(cls, ax, frame: pd.DataFrame, chart_objects: list[dict]) -> None:
        last_idx = len(frame) - 1
        for obj in chart_objects:
            obj_type = obj.get("type")
            color = obj.get("color", "#f59e0b")
            alpha = float(obj.get("alpha", 0.9))
            text = obj.get("text")

            if obj_type == ChartObjectType.HLINE.value:
                price = float(obj["price"])
                ax.axhline(price, color=color, linestyle=obj.get("linestyle", "--"), linewidth=float(obj.get("linewidth", 1.0)), alpha=alpha)
                if text:
                    cls._draw_right_edge_label(ax=ax, y=price, text=text, color=color)
            elif obj_type == ChartObjectType.ZONE.value:
                x0 = int(obj.get("start_idx", 0)) - 0.5
                x1 = last_idx + 0.5 if obj.get("extend_right") else int(obj.get("end_idx", last_idx)) + 0.5
                y0 = float(obj["low"])
                y1 = float(obj["high"])
                rect = Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=color, edgecolor=color, linewidth=1.0, alpha=float(obj.get("alpha", 0.15)))
                ax.add_patch(rect)
                if text:
                    ax.text((x0 + x1) / 2, (y0 + y1) / 2, text, ha="center", va="center", fontsize=8, fontweight="semibold", color=obj.get("text_color", "#92400e"), bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.6})

    @classmethod
    def _plot_volatility_panel(cls, *, ax, frame: pd.DataFrame, volatility_window: int) -> None:
        ax.plot(frame.index, frame["local_volatility"], color=cls.VOL_LOCAL, linewidth=1.2, label=f"Local Vol {volatility_window}")
        ax.plot(frame.index, frame["atr_pct"], color=cls.VOL_ATR, linewidth=1.0, alpha=0.9, label="ATR% 14")
        ax.plot(frame.index, frame["local_volatility_baseline"], color=cls.VOL_BASELINE, linewidth=1.0, alpha=0.85, label="Vol Baseline")

    @classmethod
    def _plot_volume_panel(cls, *, ax, frame: pd.DataFrame, volume_window: int, volume_spike_ratio: float) -> None:
        volume_colors = [cls.VOLUME_SPIKE if is_spike else cls.VOLUME_BAR for is_spike in frame["is_volume_spike"]]
        ax.bar(frame.index, frame["volume"], color=volume_colors, width=0.82, label="Volume")
        ax.plot(frame.index, frame["volume_avg"], color=cls.VOLUME_AVG, linewidth=1.1, label=f"Volume Avg {volume_window}")
        ax.plot(frame.index, frame["volume_avg"] * volume_spike_ratio, color=cls.VOLUME_SPIKE_LINE, linestyle="--", linewidth=0.9, alpha=0.85, label=f"Spike {volume_spike_ratio:.1f}x")

    @classmethod
    def _plot_delta_panel(cls, *, ax, frame: pd.DataFrame) -> None:
        velocity_colors = [cls.DELTA_POS if value >= 0 else cls.DELTA_NEG for value in frame["diff_velocity"]]
        ax.bar(frame.index, frame["diff_velocity"], color=velocity_colors, width=0.82, alpha=0.45, label="Delta Diff")
        ax.plot(frame.index, frame["diff_velocity_smooth"], color=cls.DELTA_SMOOTH, linewidth=1.3, label="Smoothed Delta")
        ax.axhline(0.0, color=cls.DELTA_ZERO, linewidth=0.9)

    @staticmethod
    def tick_positions(size: int, steps: int = 8) -> list[int]:
        if size <= 1:
            return [0]
        interval = max(1, size // steps)
        positions = list(range(0, size, interval))
        if positions[-1] != size - 1:
            positions.append(size - 1)
        return positions

    @staticmethod
    def _legend_if_needed(ax, **kwargs) -> None:
        handles, labels = ax.get_legend_handles_labels()
        pairs = [(handle, label) for handle, label in zip(handles, labels) if label and not label.startswith("_")]
        if not pairs:
            return
        legend_handles, legend_labels = zip(*pairs)
        ax.legend(legend_handles, legend_labels, **kwargs)

    @staticmethod
    def _add_price_headroom(ax, top_ratio: float = 0.05) -> None:
        ymin, ymax = ax.get_ylim()
        if not pd.notna(ymin) or not pd.notna(ymax) or ymax <= ymin:
            return
        ax.set_ylim(ymin, ymax + ((ymax - ymin) * top_ratio))

    @staticmethod
    def _resolve_bar_label_y(*, idx: int, proposed_y: float, placed_labels: list[tuple[int, float]], x_spacing: int, min_y_gap: float) -> float:
        epsilon = max(1e-12, abs(min_y_gap) * 1e-9)
        label_y = proposed_y
        max_iters = max(8, (len(placed_labels) * 4) + 8)
        for _ in range(max_iters):
            conflict = False
            for placed_idx, placed_y in placed_labels:
                if abs(idx - placed_idx) <= x_spacing and abs(label_y - placed_y) < (min_y_gap - epsilon):
                    label_y = placed_y + min_y_gap + epsilon
                    conflict = True
                    break
            if not conflict:
                return label_y
        return label_y

    @staticmethod
    def _draw_bar_label(*, ax, x: int, anchor_y: float, label_y: float, text: str, color: str) -> None:
        ax.plot([x, x], [anchor_y, label_y], color=color, linewidth=0.75, alpha=0.5, zorder=5)
        ax.text(
            x,
            label_y,
            text,
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color=color,
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.74},
            clip_on=False,
            zorder=6,
        )

    @staticmethod
    def _draw_right_edge_label(*, ax, y: float, text: str, color: str) -> None:
        edge_transform = mtransforms.blended_transform_factory(ax.transAxes, ax.transData)
        ax.annotate(
            text,
            xy=(1.0, y),
            xycoords=edge_transform,
            xytext=(-4, 1),
            textcoords="offset points",
            ha="right",
            va="bottom",
            fontsize=8,
            color=color,
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.7},
            annotation_clip=False,
            zorder=5,
        )

    @staticmethod
    def _build_title(*, frame: pd.DataFrame, symbol: str | None, zero_price: float | None) -> str:
        symbol_value = symbol
        if symbol_value is None and "symbol" in frame.columns and not frame["symbol"].empty:
            symbol_value = str(frame["symbol"].iloc[-1])

        tf_value = None
        if "tf" in frame.columns and not frame["tf"].empty:
            tf_value = str(frame["tf"].iloc[-1])

        start = frame["open_time"].iloc[0].strftime("%Y-%m-%d %H:%M")
        end = frame["open_time"].iloc[-1].strftime("%Y-%m-%d %H:%M")
        left = " | ".join(part for part in [symbol_value, f"tf={tf_value}" if tf_value else None] if part)
        if zero_price is not None:
            if left:
                return f"{left} | {start} -> {end} | zero={float(zero_price):.8g}"
            return f"{start} -> {end} | zero={float(zero_price):.8g}"
        if left:
            return f"{left} | {start} -> {end}"
        return f"{start} -> {end}"

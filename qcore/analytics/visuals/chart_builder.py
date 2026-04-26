from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from .chart_plotter import ChartPlotter
from .chart_types import ChartObjectType, IndicatorSpec, IndicatorType, MarkType


TIMEFRAME_RULES = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1D",
}


class ChartBuilder:
    def __init__(
        self,
        *,
        df_base: pd.DataFrame,
        pair: str,
        base_tf: str,
        tf: str,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
        indicator_specs: Iterable[IndicatorSpec] | None = None,
    ) -> None:
        self.pair = pair
        self.base_tf = base_tf
        self.tf = tf
        self.chart_objects: list[dict] = []
        self.indicator_specs: list[IndicatorSpec] = []

        frame = df_base.copy()
        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="raise")
        frame = frame.sort_values("open_time").reset_index(drop=True)
        if start is not None:
            frame = frame[frame["open_time"] >= self._to_utc_timestamp(start)]
        if end is not None:
            frame = frame[frame["open_time"] <= self._to_utc_timestamp(end)]
        if frame.empty:
            raise ValueError("Input dataframe is empty after applying range filters.")

        self.start = frame["open_time"].iloc[0]
        self.end = frame["open_time"].iloc[-1]
        self.df_base = self._normalize_base_frame(frame, base_tf=base_tf, pair=pair)
        self.df = self._resample_klines(self.df_base, tf)
        self._ensure_plot_ann_column()

        if indicator_specs:
            for spec in indicator_specs:
                self.add_indicator(spec)

    @classmethod
    def from_dataframe(
        cls,
        *,
        df_base: pd.DataFrame,
        pair: str,
        base_tf: str,
        tf: str,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
        indicator_specs: Iterable[IndicatorSpec] | None = None,
    ) -> "ChartBuilder":
        return cls(
            df_base=df_base,
            pair=pair,
            base_tf=base_tf,
            tf=tf,
            start=start,
            end=end,
            indicator_specs=indicator_specs,
        )

    @classmethod
    def from_parquet_files(
        cls,
        *,
        files: Iterable[str | Path],
        pair: str,
        base_tf: str,
        tf: str,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
        columns: Iterable[str] | None = None,
        indicator_specs: Iterable[IndicatorSpec] | None = None,
    ) -> "ChartBuilder":
        frames: list[pd.DataFrame] = []
        wanted_columns = list(columns) if columns is not None else None
        for raw_path in files:
            path = Path(raw_path)
            if not path.exists():
                continue
            frames.append(pd.read_parquet(path, columns=wanted_columns))
        if not frames:
            raise ValueError("No parquet files could be loaded for chart builder.")
        df_base = pd.concat(frames, ignore_index=True)
        return cls.from_dataframe(
            df_base=df_base,
            pair=pair,
            base_tf=base_tf,
            tf=tf,
            start=start,
            end=end,
            indicator_specs=indicator_specs,
        )

    def clone(self) -> "ChartBuilder":
        new = self.__class__.from_dataframe(
            df_base=self.df_base.copy(),
            pair=self.pair,
            base_tf=self.base_tf,
            tf=self.tf,
            start=self.start,
            end=self.end,
            indicator_specs=[replace(spec) for spec in self.indicator_specs],
        )
        new.chart_objects = [dict(obj) for obj in self.chart_objects]
        if "plot_ann" in self.df.columns:
            new.df["plot_ann"] = self.df["plot_ann"].apply(lambda x: [dict(i) for i in x] if isinstance(x, list) else x)
        return new

    @staticmethod
    def _to_utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")

    @staticmethod
    def _coerce_open_time(series: pd.Series) -> pd.Series:
        if pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series):
            return pd.to_datetime(series, unit="ms", utc=True, errors="raise")
        return pd.to_datetime(series, utc=True, errors="raise")

    @staticmethod
    def _normalize_base_frame(df: pd.DataFrame, *, base_tf: str, pair: str) -> pd.DataFrame:
        required = {"open_time", "open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Raw dataframe missing columns: {sorted(missing)}")

        frame = df.copy()
        frame["open_time"] = ChartBuilder._coerce_open_time(frame["open_time"])
        frame = frame.sort_values("open_time").reset_index(drop=True)

        numeric_cols = ["open", "high", "low", "close"]
        optional_numeric_cols = ["volume", "quote_asset_volume", "taker_buy_quote_asset_volume", "num_trades"]
        for col in numeric_cols + [c for c in optional_numeric_cols if c in frame.columns]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        if "symbol" not in frame.columns:
            frame["symbol"] = pair
        if "tf" not in frame.columns:
            frame["tf"] = base_tf
        return frame

    def _resample_klines(self, df: pd.DataFrame, tf: str) -> pd.DataFrame:
        if tf not in TIMEFRAME_RULES:
            raise ValueError(f"Unsupported timeframe: {tf}")

        frame = df.copy()
        frame["open_time"] = self._coerce_open_time(frame["open_time"])
        frame = frame.sort_values("open_time").set_index("open_time")

        if tf == self.base_tf:
            out = frame.reset_index()
        else:
            agg = {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
            if "quote_asset_volume" in frame.columns:
                agg["quote_asset_volume"] = "sum"
            if "taker_buy_quote_asset_volume" in frame.columns:
                agg["taker_buy_quote_asset_volume"] = "sum"
            if "num_trades" in frame.columns:
                agg["num_trades"] = "sum"
            if "symbol" in frame.columns:
                agg["symbol"] = "last"

            out = (
                frame.resample(TIMEFRAME_RULES[tf], label="left", closed="left")
                .agg(agg)
                .dropna(subset=["open", "high", "low", "close"])
                .reset_index()
            )

        out["tf"] = tf
        return out.reset_index(drop=True)

    def _ensure_plot_ann_column(self) -> None:
        if "plot_ann" not in self.df.columns:
            self.df["plot_ann"] = None
        self.df["plot_ann"] = self.df["plot_ann"].astype(object)

    def resolve_bar(self, value: int | str | pd.Timestamp) -> int:
        if isinstance(value, int):
            if value < 0 or value >= len(self.df):
                raise IndexError(f"Bar index out of range: {value}")
            return value
        ts = self._to_utc_timestamp(value)
        matches = self.df.index[self.df["open_time"] == ts]
        if len(matches) == 0:
            raise ValueError(f"Timestamp not found in resampled dataframe: {ts}")
        return int(matches[0])

    def resolve_containing_bar(self, value: str | pd.Timestamp) -> int:
        ts = self._to_utc_timestamp(value)
        series = pd.to_datetime(self.df["open_time"], utc=True, errors="raise")
        idx = int(series.searchsorted(ts, side="right") - 1)
        if idx < 0:
            return 0
        if idx >= len(self.df):
            return len(self.df) - 1
        return idx

    def resolve_range(self, start: int | str | pd.Timestamp, end: int | str | pd.Timestamp) -> tuple[int, int]:
        left = self.resolve_bar(start) if isinstance(start, int) else self.resolve_containing_bar(start)
        right = self.resolve_bar(end) if isinstance(end, int) else self.resolve_containing_bar(end)
        if left > right:
            left, right = right, left
        return left, right

    def crop_by_range(self, start_bar: int, end_bar: int) -> "ChartBuilder":
        left = max(0, int(start_bar))
        right = min(len(self.df) - 1, int(end_bar))
        if left > right:
            left, right = right, left
        self.df = self.df.iloc[left : right + 1].reset_index(drop=True)
        return self

    def add_indicator(self, spec: IndicatorSpec) -> "ChartBuilder":
        source = spec.source
        if source not in self.df.columns:
            raise ValueError(f"Indicator source column not found: {source}")
        col = spec.resolved_name()
        if spec.type == IndicatorType.EMA:
            if not spec.period:
                raise ValueError("EMA requires period")
            self.df[col] = self.df[source].ewm(span=spec.period, adjust=False).mean()
        elif spec.type == IndicatorType.SMA:
            if not spec.period:
                raise ValueError("SMA requires period")
            self.df[col] = self.df[source].rolling(spec.period, min_periods=1).mean()
        elif spec.type == IndicatorType.ATR:
            period = spec.period or 14
            prev_close = self.df["close"].shift(1)
            tr = pd.concat(
                [
                    self.df["high"] - self.df["low"],
                    (self.df["high"] - prev_close).abs(),
                    (self.df["low"] - prev_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            self.df[col] = tr.rolling(period, min_periods=1).mean()
        elif spec.type == IndicatorType.VWAP:
            typical = (self.df["high"] + self.df["low"] + self.df["close"]) / 3.0
            vol = self.df["volume"].fillna(0)
            cum_pv = (typical * vol).cumsum()
            cum_v = vol.cumsum().replace(0, pd.NA)
            self.df[col] = (cum_pv / cum_v).astype(float)
        else:
            raise ValueError(f"Unsupported indicator type: {spec.type}")
        self.indicator_specs.append(spec)
        return self

    def add_indicators(self, specs: Iterable[IndicatorSpec]) -> "ChartBuilder":
        for spec in specs:
            self.add_indicator(spec)
        return self

    def _append_bar_annotation(self, idx: int, ann: dict) -> None:
        current = self.df.at[idx, "plot_ann"]
        if current is None or (isinstance(current, float) and pd.isna(current)):
            self.df.at[idx, "plot_ann"] = [ann]
        elif isinstance(current, list):
            current.append(ann)
        else:
            self.df.at[idx, "plot_ann"] = [current, ann]

    def add_mark(
        self,
        bar: int | str | pd.Timestamp,
        *,
        mark_type: MarkType,
        text: str | None = None,
        color: str | None = None,
        alpha: float | None = None,
        containing: bool = False,
        **extra,
    ) -> "ChartBuilder":
        idx = self.resolve_containing_bar(bar) if containing and not isinstance(bar, int) else self.resolve_bar(bar)
        ann = {"type": mark_type.value}
        if text is not None:
            ann["text"] = text
        if color is not None:
            ann["color"] = color
        if alpha is not None:
            ann["alpha"] = alpha
        ann.update(extra)
        self._append_bar_annotation(idx, ann)
        return self

    def add_range(
        self,
        start_bar: int | str | pd.Timestamp,
        end_bar: int | str | pd.Timestamp,
        *,
        text: str | None = None,
        color: str = "#dcfce7",
        alpha: float = 0.22,
    ) -> "ChartBuilder":
        left, right = self.resolve_range(start_bar, end_bar)
        for idx in range(left, right + 1):
            self._append_bar_annotation(idx, {"type": MarkType.BG.value, "text": text, "color": color, "alpha": alpha})
        return self

    def add_hline(
        self,
        price: float,
        *,
        text: str | None = None,
        color: str = "#f59e0b",
        alpha: float = 0.9,
        linestyle: str = "--",
        linewidth: float = 1.0,
    ) -> "ChartBuilder":
        self.chart_objects.append({"type": ChartObjectType.HLINE.value, "price": float(price), "text": text, "color": color, "alpha": alpha, "linestyle": linestyle, "linewidth": linewidth})
        return self

    def add_zone(
        self,
        *,
        low: float,
        high: float,
        start_bar: int | str | pd.Timestamp | None = None,
        end_bar: int | str | pd.Timestamp | None = None,
        text: str | None = None,
        color: str = "#fde68a",
        alpha: float = 0.15,
        extend_right: bool = False,
    ) -> "ChartBuilder":
        start_idx = 0 if start_bar is None else self.resolve_containing_bar(start_bar) if not isinstance(start_bar, int) else self.resolve_bar(start_bar)
        end_idx = len(self.df) - 1 if end_bar is None else self.resolve_containing_bar(end_bar) if not isinstance(end_bar, int) else self.resolve_bar(end_bar)
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        self.chart_objects.append({"type": ChartObjectType.ZONE.value, "low": float(low), "high": float(high), "start_idx": start_idx, "end_idx": end_idx, "text": text, "color": color, "alpha": alpha, "extend_right": bool(extend_right)})
        return self

    def get_frame(self) -> pd.DataFrame:
        return self.df.copy()

    def plot(self, **kwargs):
        return ChartPlotter.plot(self.df, indicator_specs=self.indicator_specs, chart_objects=self.chart_objects, symbol=self.pair, **kwargs)

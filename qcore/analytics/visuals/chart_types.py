from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IndicatorType(str, Enum):
    EMA = "ema"
    SMA = "sma"
    ATR = "atr"
    VWAP = "vwap"


class MarkType(str, Enum):
    BAR_LABEL = "bar_label"
    VLINE = "vline"
    BG = "bg"


class ChartObjectType(str, Enum):
    HLINE = "hline"
    ZONE = "zone"


@dataclass(slots=True, frozen=True)
class IndicatorSpec:
    type: IndicatorType
    period: int | None = None
    source: str = "close"
    column_name: str | None = None
    color: str | None = None
    linewidth: float = 1.2
    alpha: float = 0.95
    panel: str = "price"
    extra: dict[str, Any] = field(default_factory=dict)

    def resolved_name(self) -> str:
        if self.column_name:
            return self.column_name
        if self.period is None:
            return self.type.value
        return f"{self.type.value}_{self.period}"

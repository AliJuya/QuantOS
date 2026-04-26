from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from math import sqrt

from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import ModelId
from qcore.domain.types import RegimeSnapshot, Symbol, Timeframe, VolatilitySnapshot, WarmupStatus


@dataclass(slots=True)
class EwmaVolatilityModel:
    model_id: ModelId
    timeframe: Timeframe
    lookback: int
    annualization_factor: int = 365
    returns_by_symbol: dict[Symbol, deque[Decimal]] = field(default_factory=dict)
    prev_close_by_symbol: dict[Symbol, Decimal] = field(default_factory=dict)
    warmup_ready: dict[Symbol, bool] = field(default_factory=dict)

    def on_bar_close(self, event: BarCloseEvent) -> list[object]:
        if event.timeframe != self.timeframe:
            return []

        close = event.close_price.value
        previous = self.prev_close_by_symbol.get(event.symbol)
        self.prev_close_by_symbol[event.symbol] = close

        if previous is None or previous <= 0:
            return []

        returns = self.returns_by_symbol.setdefault(event.symbol, deque(maxlen=self.lookback))
        returns.append((close / previous) - Decimal("1"))
        samples_seen = len(returns)
        emitted: list[object] = []
        ready = samples_seen >= self.lookback
        was_ready = self.warmup_ready.get(event.symbol, False)
        if not ready:
            emitted.append(
                WarmupStatus(
                    component_id=str(self.model_id),
                    symbol=event.symbol,
                    ready=False,
                    samples_seen=samples_seen,
                    samples_required=self.lookback,
                    timestamp=event.timestamp,
                )
            )
            return emitted

        if not was_ready:
            self.warmup_ready[event.symbol] = True
            emitted.append(
                WarmupStatus(
                    component_id=str(self.model_id),
                    symbol=event.symbol,
                    ready=True,
                    samples_seen=samples_seen,
                    samples_required=self.lookback,
                    timestamp=event.timestamp,
                )
            )

        mean_return = sum(returns) / Decimal(samples_seen)
        variance = sum((value - mean_return) ** 2 for value in returns) / Decimal(samples_seen)
        return_std = float(variance.sqrt() if hasattr(variance, "sqrt") else Decimal(str(sqrt(float(variance)))))
        annualized_vol = return_std * sqrt(float(self.annualization_factor))
        emitted.append(
            VolatilitySnapshot(
                model_id=self.model_id,
                symbol=event.symbol,
                timeframe=self.timeframe,
                timestamp=event.timestamp,
                annualized_vol=annualized_vol,
                return_std=return_std,
                ready=True,
                metadata={
                    "samples_seen": samples_seen,
                    "annualization_factor": self.annualization_factor,
                    "close": str(close),
                },
            )
        )
        return emitted

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        return (self.timeframe,)

    def warmup_requirements(self) -> dict[Timeframe, int]:
        return {self.timeframe: self.lookback + 1}

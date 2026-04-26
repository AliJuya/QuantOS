from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import ModelId
from qcore.domain.types import RegimeSnapshot, Symbol, Timeframe, WarmupStatus
from qcore.indicators.incremental import EMAIndicator


@dataclass(slots=True)
class EmaTrendRegimeModel:
    model_id: ModelId
    timeframe: Timeframe
    fast_period: int
    slow_period: int
    fast_ema: dict[Symbol, EMAIndicator] = field(default_factory=dict)
    slow_ema: dict[Symbol, EMAIndicator] = field(default_factory=dict)
    warmup_ready: dict[Symbol, bool] = field(default_factory=dict)

    def on_bar_close(self, event: BarCloseEvent) -> list[object]:
        if event.timeframe != self.timeframe:
            return []

        fast = self.fast_ema.setdefault(event.symbol, EMAIndicator(self.fast_period))
        slow = self.slow_ema.setdefault(event.symbol, EMAIndicator(self.slow_period))
        fast_value = fast.update(event.close_price.value)
        slow_value = slow.update(event.close_price.value)
        samples_seen = min(fast.samples_seen, slow.samples_seen)
        emitted: list[object] = []
        ready = fast.ready and slow.ready
        was_ready = self.warmup_ready.get(event.symbol, False)
        if not ready:
            emitted.append(
                WarmupStatus(
                    component_id=str(self.model_id),
                    symbol=event.symbol,
                    ready=False,
                    samples_seen=samples_seen,
                    samples_required=max(self.fast_period, self.slow_period),
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
                    samples_required=max(self.fast_period, self.slow_period),
                    timestamp=event.timestamp,
                )
            )

        regime = "neutral"
        if fast_value > slow_value:
            regime = "bull"
        elif fast_value < slow_value:
            regime = "bear"

        close = event.close_price.value
        score = float(abs(fast_value - slow_value) / close) if close != 0 else 0.0
        emitted.append(
            RegimeSnapshot(
                model_id=self.model_id,
                symbol=event.symbol,
                timeframe=self.timeframe,
                timestamp=event.timestamp,
                regime=regime,
                score=score,
                ready=True,
                metadata={
                    "fast_ema": str(fast_value),
                    "slow_ema": str(slow_value),
                    "close": str(close),
                },
            )
        )
        return emitted

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        return (self.timeframe,)

    def warmup_requirements(self) -> dict[Timeframe, int]:
        return {self.timeframe: max(self.fast_period, self.slow_period)}

from __future__ import annotations

from dataclasses import dataclass

from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import AlphaId, StrategyId
from qcore.domain.types import AlphaSignal, Timeframe


@dataclass(slots=True)
class StrategyTemplate:
    """
    Minimal template for a QuantOS alpha strategy.

    Steps:
    1. Copy this file.
    2. Rename the class.
    3. Implement on_bar_close().
    4. Register the strategy in qcore/registry/strategies.py.
    5. Add a config entry under configs/app/.
    """

    strategy_id: StrategyId
    signal_horizon: Timeframe
    input_timeframe: Timeframe

    def on_bar_close(self, event: BarCloseEvent) -> list[object]:
        if event.timeframe != self.input_timeframe:
            return []

        emitted: list[object] = []

        # Replace this condition with real strategy logic.
        if event.close_price.value > event.open_price.value:
            emitted.append(
                AlphaSignal(
                    alpha_id=AlphaId(f"{self.strategy_id}:{event.symbol}:{event.timestamp.isoformat()}"),
                    strategy_id=self.strategy_id,
                    symbol=event.symbol,
                    side=SignalSide.LONG,
                    confidence=0.50,
                    horizon=self.signal_horizon,
                    entry_style=EntryStyle.TREND,
                    thesis="Template bullish close",
                    invalidation="Template invalidation",
                    timestamp=event.timestamp,
                    features_ref=None,
                    metadata={"template": True},
                )
            )

        return emitted

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        return (self.input_timeframe,)

    def warmup_requirements(self) -> dict[Timeframe, int]:
        return {self.input_timeframe: 1}

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcore.domain.enums import EntryStyle, SignalSide
from qcore.domain.events import BarCloseEvent
from qcore.domain.ids import AlphaId, StrategyId
from qcore.domain.types import AlphaSignal, ExitPolicy, Price, Symbol, Timeframe, TrailingStopPolicy, WarmupStatus
from qcore.indicators.incremental import EMAIndicator


@dataclass(slots=True)
class EmaCrossStrategy:
    strategy_id: StrategyId
    short_period: int
    long_period: int
    signal_horizon: Timeframe
    input_timeframe: Timeframe | None = None
    stop_loss_fraction: float | None = None
    take_profit_fraction: float | None = None
    trailing_stop_fraction: float | None = None
    trailing_stop_amount: float | None = None
    max_hold_bars: int | None = None
    exit_on_session_close: bool = False
    last_relation: dict[Symbol, int] = field(default_factory=dict)
    short_ema: dict[Symbol, EMAIndicator] = field(default_factory=dict)
    long_ema: dict[Symbol, EMAIndicator] = field(default_factory=dict)
    warmup_ready: dict[Symbol, bool] = field(default_factory=dict)

    def on_bar_close(self, event: BarCloseEvent) -> list[object]:
        if self.input_timeframe is not None and event.timeframe != self.input_timeframe:
            return []

        short = self.short_ema.setdefault(event.symbol, EMAIndicator(self.short_period))
        long = self.long_ema.setdefault(event.symbol, EMAIndicator(self.long_period))

        short_value = short.update(event.close_price.value)
        long_value = long.update(event.close_price.value)

        emitted: list[object] = []
        ready = short.ready and long.ready
        was_ready = self.warmup_ready.get(event.symbol, False)
        if not ready:
            emitted.append(
                WarmupStatus(
                    component_id=str(self.strategy_id),
                    symbol=event.symbol,
                    ready=False,
                    samples_seen=min(short.samples_seen, long.samples_seen),
                    samples_required=max(self.short_period, self.long_period),
                    timestamp=event.timestamp,
                )
            )
            return emitted

        if not was_ready:
            self.warmup_ready[event.symbol] = True
            emitted.append(
                WarmupStatus(
                    component_id=str(self.strategy_id),
                    symbol=event.symbol,
                    ready=True,
                    samples_seen=min(short.samples_seen, long.samples_seen),
                    samples_required=max(self.short_period, self.long_period),
                    timestamp=event.timestamp,
                )
            )

        relation = self._relation(short_value, long_value)
        previous = self.last_relation.get(event.symbol)
        self.last_relation[event.symbol] = relation
        if previous is None or relation == 0 or relation == previous:
            return emitted

        side = SignalSide.LONG if relation > 0 else SignalSide.SHORT
        spread = abs(short_value - long_value)
        confidence = float(min(spread / event.close_price.value, Decimal("1")))
        emitted.append(
            AlphaSignal(
                alpha_id=AlphaId(f"{self.strategy_id}:{event.symbol}:{event.timestamp.isoformat()}"),
                strategy_id=self.strategy_id,
                symbol=event.symbol,
                side=side,
                confidence=confidence,
                horizon=self.signal_horizon,
                entry_style=EntryStyle.TREND,
                thesis=f"EMA{self.short_period}/{self.long_period} crossover",
                invalidation="Opposite EMA crossover",
                timestamp=event.timestamp,
                features_ref=None,
                exit_policy=self._exit_policy(side, event.close_price.value),
                metadata={
                    "short_ema": str(short_value),
                    "long_ema": str(long_value),
                    "close": str(event.close_price.value),
                },
            )
        )
        return emitted

    @staticmethod
    def _relation(short_value: Decimal, long_value: Decimal) -> int:
        if short_value > long_value:
            return 1
        if short_value < long_value:
            return -1
        return 0

    def required_timeframes(self) -> tuple[Timeframe, ...]:
        if self.input_timeframe is None:
            return ()
        return (self.input_timeframe,)

    def warmup_requirements(self) -> dict[Timeframe, int]:
        if self.input_timeframe is None:
            return {}
        return {self.input_timeframe: max(self.short_period, self.long_period)}

    def _exit_policy(self, side: SignalSide, close_value: Decimal) -> ExitPolicy | None:
        stop_loss: Price | None = None
        take_profit: Price | None = None

        if self.stop_loss_fraction is not None:
            fraction = Decimal(str(self.stop_loss_fraction))
            if side is SignalSide.LONG:
                stop_loss = Price(close_value * (Decimal("1") - fraction))
            elif side is SignalSide.SHORT:
                stop_loss = Price(close_value * (Decimal("1") + fraction))
        if self.take_profit_fraction is not None:
            fraction = Decimal(str(self.take_profit_fraction))
            if side is SignalSide.LONG:
                take_profit = Price(close_value * (Decimal("1") + fraction))
            elif side is SignalSide.SHORT:
                take_profit = Price(close_value * (Decimal("1") - fraction))

        trailing_stop = None
        if self.trailing_stop_fraction is not None or self.trailing_stop_amount is not None:
            trailing_stop = TrailingStopPolicy(
                trail_fraction=Decimal(str(self.trailing_stop_fraction)) if self.trailing_stop_fraction is not None else None,
                trail_amount=Decimal(str(self.trailing_stop_amount)) if self.trailing_stop_amount is not None else None,
            )

        if (
            stop_loss is None
            and take_profit is None
            and trailing_stop is None
            and self.max_hold_bars is None
            and not self.exit_on_session_close
        ):
            return None

        return ExitPolicy(
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=trailing_stop,
            max_hold_bars=self.max_hold_bars,
            exit_on_session_close=self.exit_on_session_close,
        )

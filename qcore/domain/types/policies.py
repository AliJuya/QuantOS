from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from qcore.domain.types.primitives import Price, to_decimal


JsonMap = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TrailingStopPolicy:
    trail_fraction: Decimal | None = None
    trail_amount: Decimal | None = None
    activation_fraction: Decimal | None = None
    activation_amount: Decimal | None = None

    def __post_init__(self) -> None:
        if (self.trail_fraction is None) == (self.trail_amount is None):
            raise ValueError("exactly one of trail_fraction or trail_amount must be set")
        if self.activation_fraction is not None and self.activation_amount is not None:
            raise ValueError("at most one of activation_fraction or activation_amount may be set")
        if self.trail_fraction is not None:
            value = to_decimal(self.trail_fraction)
            if value <= 0:
                raise ValueError("trail_fraction must be positive")
            object.__setattr__(self, "trail_fraction", value)
        if self.trail_amount is not None:
            value = to_decimal(self.trail_amount)
            if value <= 0:
                raise ValueError("trail_amount must be positive")
            object.__setattr__(self, "trail_amount", value)
        if self.activation_fraction is not None:
            value = to_decimal(self.activation_fraction)
            if value <= 0:
                raise ValueError("activation_fraction must be positive")
            object.__setattr__(self, "activation_fraction", value)
        if self.activation_amount is not None:
            value = to_decimal(self.activation_amount)
            if value <= 0:
                raise ValueError("activation_amount must be positive")
            object.__setattr__(self, "activation_amount", value)


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    stop_loss: Price | None = None
    take_profit: Price | None = None
    trailing_stop: TrailingStopPolicy | None = None
    max_hold_bars: int | None = None
    exit_on_session_close: bool = False
    metadata: JsonMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_hold_bars is not None and self.max_hold_bars <= 0:
            raise ValueError("max_hold_bars must be positive when provided")

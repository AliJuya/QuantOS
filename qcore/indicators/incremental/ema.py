from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from qcore.domain.types import to_decimal


@dataclass(slots=True)
class EMAIndicator:
    period: int
    value: Decimal | None = None
    samples_seen: int = 0
    _multiplier: Decimal = field(init=False)

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("EMA period must be positive")
        self._multiplier = Decimal("2") / Decimal(str(self.period + 1))

    @property
    def ready(self) -> bool:
        return self.samples_seen >= self.period

    @property
    def remaining(self) -> int:
        return max(self.period - self.samples_seen, 0)

    def update(self, price: Decimal | float | int | str) -> Decimal:
        current_price = to_decimal(price)
        if self.value is None:
            self.value = current_price
        else:
            self.value = ((current_price - self.value) * self._multiplier) + self.value
        self.samples_seen += 1
        return self.value

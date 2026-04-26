from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any


def to_decimal(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


@lru_cache(maxsize=64)
def parse_timeframe(value: str) -> timedelta:
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    if len(value) < 2 or value[-1] not in units:
        raise ValueError(f"unsupported timeframe: {value}")
    magnitude = int(value[:-1])
    return timedelta(seconds=magnitude * units[value[-1]])


@dataclass(frozen=True, slots=True)
class Symbol:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("symbol must be non-empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Venue:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("venue must be non-empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Timeframe:
    value: str

    def __post_init__(self) -> None:
        parse_timeframe(self.value)

    @property
    def duration(self) -> timedelta:
        return parse_timeframe(self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        if not self.currency:
            raise ValueError("currency must be non-empty")

    @classmethod
    def zero(cls, currency: str = "USD") -> "Money":
        return cls(amount=Decimal("0"), currency=currency)


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", to_decimal(self.value))

    def abs(self) -> "Quantity":
        return Quantity(abs(self.value))


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal

    def __post_init__(self) -> None:
        decimal_value = to_decimal(self.value)
        if decimal_value <= 0:
            raise ValueError("price must be positive")
        object.__setattr__(self, "value", decimal_value)


def primitive_to_python(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    return value

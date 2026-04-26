from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qcore.domain.types import ensure_utc


@dataclass(slots=True)
class ReplayClock:
    _current: datetime | None = None

    def now(self) -> datetime | None:
        return self._current

    def advance_to(self, timestamp: datetime) -> datetime:
        utc_timestamp = ensure_utc(timestamp)
        if self._current is not None and utc_timestamp < self._current:
            raise ValueError("replay clock cannot move backwards")
        self._current = utc_timestamp
        return utc_timestamp


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Protocol

from qcore.domain.types import ensure_utc


@dataclass(frozen=True, slots=True)
class SessionContext:
    timestamp_utc: datetime
    local_timestamp: datetime
    calendar_id: str
    session_label: str
    is_open: bool
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", ensure_utc(self.timestamp_utc))


class TradingCalendarProtocol(Protocol):
    def session_context(self, timestamp: datetime) -> SessionContext: ...

    def stats(self) -> Mapping[str, object]: ...

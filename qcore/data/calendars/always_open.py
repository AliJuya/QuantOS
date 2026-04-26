from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from qcore.data.calendars.base import SessionContext
from qcore.domain.types import ensure_utc


@dataclass(frozen=True, slots=True)
class AlwaysOpenCalendar:
    calendar_id: str = "always_open"
    timezone_name: str = "UTC"
    session_label: str = "all_session"

    def session_context(self, timestamp: datetime) -> SessionContext:
        timestamp_utc = ensure_utc(timestamp)
        local_timestamp = timestamp_utc.astimezone(ZoneInfo(self.timezone_name))
        return SessionContext(
            timestamp_utc=timestamp_utc,
            local_timestamp=local_timestamp,
            calendar_id=self.calendar_id,
            session_label=self.session_label,
            is_open=True,
            metadata={"timezone": self.timezone_name},
        )

    def stats(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "kind": "always_open",
            "timezone": self.timezone_name,
            "session_label": self.session_label,
        }

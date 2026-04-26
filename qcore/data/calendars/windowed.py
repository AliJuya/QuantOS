from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from qcore.data.calendars.base import SessionContext
from qcore.domain.types import ensure_utc


@dataclass(frozen=True, slots=True)
class SessionWindow:
    label: str
    start_hour: int
    end_hour: int
    start_minute: int = 0
    end_minute: int = 0
    weekdays_only: bool = False

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("session window label must be non-empty")
        for value in (self.start_hour, self.end_hour):
            if not 0 <= value <= 23:
                raise ValueError("session hours must be in [0, 23]")
        for value in (self.start_minute, self.end_minute):
            if not 0 <= value <= 59:
                raise ValueError("session minutes must be in [0, 59]")

    def contains(self, timestamp: datetime) -> bool:
        if self.weekdays_only and timestamp.weekday() >= 5:
            return False

        current = timestamp.timetz().replace(tzinfo=None)
        start = time(self.start_hour, self.start_minute)
        end = time(self.end_hour, self.end_minute)

        if start < end:
            return start <= current < end
        return current >= start or current < end


@dataclass(frozen=True, slots=True)
class WindowedSessionCalendar:
    calendar_id: str
    timezone_name: str = "UTC"
    session_windows: tuple[SessionWindow, ...] = ()
    out_of_session_label: str = "out_of_session"

    def __post_init__(self) -> None:
        if not self.calendar_id:
            raise ValueError("calendar_id must be non-empty")

    def session_context(self, timestamp: datetime) -> SessionContext:
        timestamp_utc = ensure_utc(timestamp)
        local_timestamp = timestamp_utc.astimezone(ZoneInfo(self.timezone_name))

        for window in self.session_windows:
            if window.contains(local_timestamp):
                return SessionContext(
                    timestamp_utc=timestamp_utc,
                    local_timestamp=local_timestamp,
                    calendar_id=self.calendar_id,
                    session_label=window.label,
                    is_open=True,
                    metadata={"timezone": self.timezone_name, "window": window.label},
                )

        return SessionContext(
            timestamp_utc=timestamp_utc,
            local_timestamp=local_timestamp,
            calendar_id=self.calendar_id,
            session_label=self.out_of_session_label,
            is_open=False,
            metadata={"timezone": self.timezone_name},
        )

    def stats(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "kind": "windowed",
            "timezone": self.timezone_name,
            "out_of_session_label": self.out_of_session_label,
            "windows": [
                {
                    "label": window.label,
                    "start": f"{window.start_hour:02d}:{window.start_minute:02d}",
                    "end": f"{window.end_hour:02d}:{window.end_minute:02d}",
                    "weekdays_only": window.weekdays_only,
                }
                for window in self.session_windows
            ],
        }

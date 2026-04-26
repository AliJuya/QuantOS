from __future__ import annotations

from typing import Any

from qcore.data.calendars import AlwaysOpenCalendar, SessionWindow, WindowedSessionCalendar
from qcore.registry.base import ComponentRegistry

_registry: ComponentRegistry[object] = ComponentRegistry("calendar")


def _build_always_open(cfg: dict[str, Any]) -> AlwaysOpenCalendar:
    return AlwaysOpenCalendar(
        calendar_id=str(cfg.get("calendar_id", "always_open")),
        timezone_name=str(cfg.get("timezone", "UTC")),
        session_label=str(cfg.get("session_label", "all_session")),
    )


def _build_windowed(cfg: dict[str, Any]) -> WindowedSessionCalendar:
    windows = tuple(
        SessionWindow(
            label=str(w["label"]),
            start_hour=int(w["start_hour"]),
            end_hour=int(w["end_hour"]),
            start_minute=int(w.get("start_minute", 0)),
            end_minute=int(w.get("end_minute", 0)),
            weekdays_only=bool(w.get("weekdays_only", False)),
        )
        for w in cfg.get("windows", ())
    )
    return WindowedSessionCalendar(
        calendar_id=str(cfg.get("calendar_id", "windowed")),
        timezone_name=str(cfg.get("timezone", "UTC")),
        session_windows=windows,
        out_of_session_label=str(cfg.get("out_of_session_label", "out_of_session")),
    )


_registry.register("always_open", _build_always_open)
_registry.register("windowed", _build_windowed)


def build_calendar(cfg: dict[str, Any]) -> object:
    kind = str(cfg.get("kind", "always_open")).strip().lower()
    return _registry.build({**cfg, "kind": kind})

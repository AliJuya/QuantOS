from datetime import UTC, datetime

from qcore.data.calendars import AlwaysOpenCalendar, SessionWindow, WindowedSessionCalendar


def test_always_open_calendar_marks_everything_open() -> None:
    calendar = AlwaysOpenCalendar(calendar_id="crypto_24x7", timezone_name="UTC", session_label="all_session")

    context = calendar.session_context(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    assert context.is_open is True
    assert context.session_label == "all_session"
    assert context.calendar_id == "crypto_24x7"


def test_windowed_calendar_classifies_named_sessions_and_out_of_session() -> None:
    calendar = WindowedSessionCalendar(
        calendar_id="utc_sessions",
        timezone_name="UTC",
        session_windows=(
            SessionWindow(label="asia", start_hour=0, end_hour=8),
            SessionWindow(label="ny", start_hour=12, end_hour=20),
        ),
        out_of_session_label="out_of_session",
    )

    asia = calendar.session_context(datetime(2026, 1, 1, 3, 0, tzinfo=UTC))
    ny = calendar.session_context(datetime(2026, 1, 1, 15, 0, tzinfo=UTC))
    out = calendar.session_context(datetime(2026, 1, 1, 9, 30, tzinfo=UTC))

    assert asia.session_label == "asia"
    assert asia.is_open is True
    assert ny.session_label == "ny"
    assert ny.is_open is True
    assert out.session_label == "out_of_session"
    assert out.is_open is False

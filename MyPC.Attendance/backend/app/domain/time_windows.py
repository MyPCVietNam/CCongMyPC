"""Local-time window helpers. End semantics use half-open intervals [start, end)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_hms(value: str) -> time:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"expected HH:MM:SS, got {value!r}")
    h, m, s = (int(parts[0]), int(parts[1]), int(parts[2]))
    return time(h, m, s)


def combine_local(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond, tzinfo=LOCAL_TZ)


def window_bounds(work_date: date, start_hms: str, end_exclusive_hms: str) -> tuple[datetime, datetime]:
    start = combine_local(work_date, parse_hms(start_hms))
    end = combine_local(work_date, parse_hms(end_exclusive_hms))
    if end <= start:
        # cross-midnight support for future shifts
        end = end + timedelta(days=1)
    return start, end


def window_contains(observed_local: datetime, work_date: date, start_hms: str, end_exclusive_hms: str) -> bool:
    if observed_local.tzinfo is None:
        raise ValueError("observed_local must be timezone-aware")
    local = observed_local.astimezone(LOCAL_TZ)
    start, end = window_bounds(work_date, start_hms, end_exclusive_hms)
    return start <= local < end


def morning_window_end_exclusive(morning_recognition_end_inclusive_hms: str) -> str:
    """
    Spec retains second-level end semantics for morning: timestamps through
    HH:MM:SS.999… are included. Model as end_exclusive = inclusive + 1 second.
    Example: 08:45:00 inclusive end → exclusive 08:45:01.
    """
    t = parse_hms(morning_recognition_end_inclusive_hms)
    base = datetime(2000, 1, 1, t.hour, t.minute, t.second)
    exclusive = base + timedelta(seconds=1)
    return exclusive.strftime("%H:%M:%S")


def abs_seconds_from_anchor(observed_local: datetime, work_date: date, anchor_hms: str) -> float:
    local = observed_local.astimezone(LOCAL_TZ)
    anchor = combine_local(work_date, parse_hms(anchor_hms))
    return abs((local - anchor).total_seconds())

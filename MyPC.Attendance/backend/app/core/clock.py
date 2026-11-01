"""Deterministic clock abstraction for production and tests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class Clock(ABC):
    @abstractmethod
    def now_utc(self) -> datetime:
        raise NotImplementedError

    def now_local(self) -> datetime:
        return self.now_utc().astimezone(LOCAL_TZ)


class SystemClock(Clock):
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock(Clock):
    """Test clock — freeze or advance explicitly."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FrozenClock requires timezone-aware datetime")
        self._instant = instant.astimezone(timezone.utc)

    def now_utc(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FrozenClock requires timezone-aware datetime")
        self._instant = instant.astimezone(timezone.utc)

    def advance(self, **kwargs) -> datetime:
        from datetime import timedelta

        self._instant = self._instant + timedelta(**kwargs)
        return self._instant


def to_local(dt: datetime) -> datetime:
    """Convert to Asia/Ho_Chi_Minh. Naive values are treated as UTC (SQLite round-trip)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_wall(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=LOCAL_TZ)

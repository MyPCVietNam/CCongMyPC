"""Canonical UTC helpers for SQLite-safe comparisons and HMAC payloads."""

from __future__ import annotations

from datetime import datetime, timezone


class AmbiguousTimestampError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_aware(dt: datetime | None) -> datetime | None:
    """Treat naive DB values as UTC; convert aware values to UTC."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        raise AmbiguousTimestampError("Giá trị thời gian không phải datetime.")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_utc_z(dt: datetime) -> str:
    """
    Stable Zulu representation independent of SQLAlchemy/SQLite tz rehydration.
    Example: 2026-11-02T03:15:00.000123Z
    """
    aware = to_utc_aware(dt)
    if aware is None:
        raise AmbiguousTimestampError("Thiếu thời gian UTC.")
    return f"{aware.strftime('%Y-%m-%dT%H:%M:%S')}.{aware.microsecond:06d}Z"


def parse_canonical_utc_z(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.endswith("Z") or "T" not in value:
        raise AmbiguousTimestampError("Định dạng thời gian canonical không hợp lệ.")
    try:
        body = value[:-1]  # drop Z
        dt = datetime.fromisoformat(body)
    except ValueError as exc:
        raise AmbiguousTimestampError("Không phân tích được thời gian UTC.") from exc
    if dt.tzinfo is not None:
        raise AmbiguousTimestampError("Canonical UTC phải không kèm offset ngoài Z.")
    return dt.replace(tzinfo=timezone.utc)

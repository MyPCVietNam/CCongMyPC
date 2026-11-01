"""Morning check-in rules — first confident observation in AM window wins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from app.domain.time_windows import (
    LOCAL_TZ,
    combine_local,
    morning_window_end_exclusive,
    parse_hms,
    window_contains,
)


class MorningStatus(str, Enum):
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    EARLY_ARRIVAL = "EARLY_ARRIVAL"
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    EXEMPT_LEAVE = "EXEMPT_LEAVE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class MorningDecision:
    status: MorningStatus
    authoritative: bool
    observed_at_local: datetime | None
    late_seconds: float
    message_vi: str


@dataclass(frozen=True, slots=True)
class MorningConfig:
    work_date: date
    window_start: str = "08:15:00"
    window_end_inclusive: str = "08:45:00"
    shift_start: str = "08:30:00"
    late_tolerance_seconds: int = 0
    morning_leave_approved: bool = False


def evaluate_morning_observation(
    observed_at_local: datetime,
    cfg: MorningConfig,
    *,
    existing_authoritative_at: datetime | None = None,
    ambiguous: bool = False,
) -> MorningDecision:
    if ambiguous:
        return MorningDecision(
            status=MorningStatus.AMBIGUOUS,
            authoritative=False,
            observed_at_local=observed_at_local,
            late_seconds=0.0,
            message_vi="Không tìm thấy khuôn mặt phù hợp. Hãy thử lại hoặc dùng phương án chấm công thay thế.",
        )

    if cfg.morning_leave_approved:
        return MorningDecision(
            status=MorningStatus.EXEMPT_LEAVE,
            authoritative=False,
            observed_at_local=observed_at_local,
            late_seconds=0.0,
            message_vi="Nghỉ phép buổi sáng đã duyệt",
        )

    end_excl = morning_window_end_exclusive(cfg.window_end_inclusive)
    if not window_contains(observed_at_local, cfg.work_date, cfg.window_start, end_excl):
        return MorningDecision(
            status=MorningStatus.OUTSIDE_WINDOW,
            authoritative=False,
            observed_at_local=observed_at_local,
            late_seconds=0.0,
            message_vi="Ngoài cửa sổ nhận diện sáng",
        )

    if existing_authoritative_at is not None:
        return MorningDecision(
            status=MorningStatus.DUPLICATE_IGNORED,
            authoritative=False,
            observed_at_local=existing_authoritative_at.astimezone(LOCAL_TZ),
            late_seconds=_late_seconds(existing_authoritative_at, cfg),
            message_vi="Đã có chấm công sáng — bỏ qua lần nhận diện sau",
        )

    late = _late_seconds(observed_at_local, cfg)
    shift = combine_local(cfg.work_date, parse_hms(cfg.shift_start))
    local = observed_at_local.astimezone(LOCAL_TZ)

    if late > 0:
        minutes = int(late // 60)
        rem_ms_note = ""
        if late < 1:
            rem_ms_note = " (dưới 1 giây)"
        return MorningDecision(
            status=MorningStatus.LATE,
            authoritative=True,
            observed_at_local=local,
            late_seconds=late,
            message_vi=f"Đi muộn {minutes} phút{rem_ms_note}" if minutes >= 1 else f"Đi muộn{rem_ms_note}",
        )

    if local < shift:
        return MorningDecision(
            status=MorningStatus.EARLY_ARRIVAL,
            authoritative=True,
            observed_at_local=local,
            late_seconds=0.0,
            message_vi="Đã ghi nhận chấm công sáng (đến sớm)",
        )

    return MorningDecision(
        status=MorningStatus.ON_TIME,
        authoritative=True,
        observed_at_local=local,
        late_seconds=0.0,
        message_vi="Đã ghi nhận chấm công sáng",
    )


def _late_seconds(observed_at_local: datetime, cfg: MorningConfig) -> float:
    local = observed_at_local.astimezone(LOCAL_TZ)
    shift = combine_local(cfg.work_date, parse_hms(cfg.shift_start))
    # ON_TIME at exact shift start; any positive amount afterward is LATE
    delta = (local - shift).total_seconds() - cfg.late_tolerance_seconds
    return delta if delta > 0 else 0.0


def scheduled_work_minutes() -> dict[str, int]:
    """Canonical scheduled durations — no payroll."""
    return {
        "morning_minutes": 210,  # 08:30–12:00
        "afternoon_minutes": 270,  # 13:30–18:00
        "lunch_minutes": 90,
        "scheduled_work_minutes": 480,
    }

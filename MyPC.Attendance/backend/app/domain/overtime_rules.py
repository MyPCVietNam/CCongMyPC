"""Overtime interval state machine — independent of afternoon reference selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from app.domain.time_windows import LOCAL_TZ, combine_local, parse_hms


class OvertimeState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    AUTO_RECORDED = "AUTO_RECORDED"
    PENDING_REVIEW = "PENDING_REVIEW"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    CORRECTED = "CORRECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class OvertimeConfig:
    work_date: date
    boundary: str = "18:00:00"
    monitor_end_exclusive: str = "23:56:00"


@dataclass(frozen=True, slots=True)
class OvertimeStartDecision:
    state: OvertimeState
    start_at_local: datetime | None
    provisional: bool
    message_vi: str


def evaluate_overtime_start(
    *,
    cfg: OvertimeConfig,
    continuous_through_boundary: bool,
    first_post_boundary_at: datetime | None,
    pm_reference_only_at: datetime | None = None,
) -> OvertimeStartDecision:
    """
    A PM reference photo alone (e.g. 17:58) does NOT prove post-18:00 work.
    """
    boundary = combine_local(cfg.work_date, parse_hms(cfg.boundary))

    if continuous_through_boundary and first_post_boundary_at is not None:
        return OvertimeStartDecision(
            state=OvertimeState.ACTIVE,
            start_at_local=boundary,
            provisional=False,
            message_vi="Đang theo dõi tăng ca",
        )

    if first_post_boundary_at is not None:
        local = first_post_boundary_at.astimezone(LOCAL_TZ)
        if local > boundary:
            return OvertimeStartDecision(
                state=OvertimeState.CANDIDATE,
                start_at_local=local,
                provisional=True,
                message_vi="Bắt đầu tăng ca tạm thời theo quan sát sau 18:00 — cần đối soát",
            )

    if pm_reference_only_at is not None and first_post_boundary_at is None:
        return OvertimeStartDecision(
            state=OvertimeState.NOT_STARTED,
            start_at_local=None,
            provisional=False,
            message_vi="Ảnh điểm danh chiều không chứng minh tăng ca",
        )

    return OvertimeStartDecision(
        state=OvertimeState.NOT_STARTED,
        start_at_local=None,
        provisional=False,
        message_vi="Chưa có dấu hiệu tăng ca",
    )


def evaluate_overtime_end(
    *,
    state: OvertimeState,
    verified_exit_at: datetime | None,
    last_observed_at: datetime | None,
    at_monitor_cutoff: bool,
    camera_lost: bool = False,
) -> tuple[OvertimeState, datetime | None, str]:
    if camera_lost and state in {OvertimeState.ACTIVE, OvertimeState.CANDIDATE}:
        return (
            OvertimeState.PENDING_REVIEW,
            None,
            "Mất kết nối camera — không thể xác minh giờ ra về",
        )

    if verified_exit_at is not None and state in {
        OvertimeState.ACTIVE,
        OvertimeState.CANDIDATE,
    }:
        return (
            OvertimeState.AUTO_RECORDED,
            verified_exit_at.astimezone(LOCAL_TZ),
            "Đã ghi nhận ra về đã xác minh",
        )

    if at_monitor_cutoff and state in {OvertimeState.ACTIVE, OvertimeState.CANDIDATE}:
        # NEVER treat 23:55 as exit time
        return (
            OvertimeState.PENDING_REVIEW,
            None,
            "Chưa xác minh được giờ ra về — hết cửa sổ theo dõi",
        )

    if last_observed_at is not None and state == OvertimeState.ACTIVE and verified_exit_at is None:
        return (
            state,
            None,
            "Xuất hiện lần cuối chưa phải ra về đã xác minh",
        )

    return state, None, ""


def duration_seconds(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()

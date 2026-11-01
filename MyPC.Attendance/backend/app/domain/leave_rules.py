"""Leave exemptions affect EXPECTED attendance, not source timestamps."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LeaveKind(str, Enum):
    FULL_DAY = "FULL_DAY"
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    HOURLY = "HOURLY"
    OFFSITE = "OFFSITE"


@dataclass(frozen=True, slots=True)
class LeaveExemption:
    kind: LeaveKind
    approved: bool


@dataclass(frozen=True, slots=True)
class AttendanceExpectation:
    morning_required: bool
    afternoon_reference_required: bool
    message_vi: str


def expectations(leave: LeaveExemption | None) -> AttendanceExpectation:
    if leave is None or not leave.approved:
        return AttendanceExpectation(
            morning_required=True,
            afternoon_reference_required=True,
            message_vi="Yêu cầu chấm công sáng và điểm danh chiều",
        )
    if leave.kind == LeaveKind.FULL_DAY:
        return AttendanceExpectation(
            morning_required=False,
            afternoon_reference_required=False,
            message_vi="Nghỉ phép cả ngày đã duyệt",
        )
    if leave.kind == LeaveKind.MORNING:
        return AttendanceExpectation(
            morning_required=False,
            afternoon_reference_required=True,
            message_vi="Nghỉ phép buổi sáng đã duyệt — vẫn cần điểm danh chiều",
        )
    if leave.kind == LeaveKind.AFTERNOON:
        return AttendanceExpectation(
            morning_required=True,
            afternoon_reference_required=False,
            message_vi="Nghỉ phép buổi chiều đã duyệt",
        )
    if leave.kind == LeaveKind.OFFSITE:
        return AttendanceExpectation(
            morning_required=False,
            afternoon_reference_required=False,
            message_vi="Nhân viên đang làm việc ngoài công ty",
        )
    return AttendanceExpectation(
        morning_required=True,
        afternoon_reference_required=True,
        message_vi="Ngoại lệ theo giờ — cần người phụ trách tính công đối soát",
    )

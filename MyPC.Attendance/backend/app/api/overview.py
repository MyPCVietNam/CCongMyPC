"""Dashboard overview aggregates."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AppState, get_app_state, get_current_user, get_db
from app.models.entities import AttendanceEvent, CameraDevice, Employee

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("")
def overview(
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    work_date: date | None = Query(None),
) -> dict:
    wd = work_date or state.clock.now_local().date()
    total_staff = db.scalar(
        select(func.count()).select_from(Employee).where(Employee.active.is_(True))
    ) or 0
    morning_count = db.scalar(
        select(func.count()).select_from(AttendanceEvent).where(
            AttendanceEvent.work_date == wd,
            AttendanceEvent.event_type == "MORNING_CHECK_IN",
        )
    ) or 0
    afternoon_count = db.scalar(
        select(func.count()).select_from(AttendanceEvent).where(
            AttendanceEvent.work_date == wd,
            AttendanceEvent.event_type == "AFTERNOON_REFERENCE",
        )
    ) or 0
    late_count = db.scalar(
        select(func.count()).select_from(AttendanceEvent).where(
            AttendanceEvent.work_date == wd,
            AttendanceEvent.event_type == "MORNING_CHECK_IN",
            AttendanceEvent.late_seconds > 0,
        )
    ) or 0
    cams = db.scalars(select(CameraDevice)).all()
    if not cams:
        cam_status_vi = "Chưa cấu hình"
    elif any(c.mock_mode for c in cams):
        cam_status_vi = "Đang kết nối (mô phỏng)"
    else:
        cam_status_vi = "Chưa cấu hình" if not any(c.enabled for c in cams) else "Chờ kiểm tra"

    return {
        "work_date": wd.isoformat(),
        "camera_status_vi": cam_status_vi,
        "camera_note_vi": "Không thể kết luận vắng mặt khi camera mất kết nối",
        "total_staff": total_staff,
        "morning_present": morning_count,
        "morning_late": late_count,
        "afternoon_present": afternoon_count,
        "overtime": {
            "active": 0,
            "confirmed": 0,
            "needs_review": 0,
            "note_vi": "Theo dõi tăng ca sẽ mở rộng ở P04",
        },
        "config_version": state.config_service.active.version,
        "mock_indicator_vi": "Dữ liệu mô phỏng" if state.camera.state.mock_mode else None,
        "afternoon_window": {
            "start": state.config_service.active.windows.afternoon_recognition_start,
            "end_exclusive": state.config_service.active.windows.afternoon_recognition_end_exclusive,
            "reference": state.config_service.active.windows.afternoon_selection.reference_time,
        },
        "exit_verification_gate": state.config_service.active.exit_verification_gate,
    }

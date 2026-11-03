"""Dashboard overview aggregates."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from app.api.db_finalize_route import FinalizingAPIRoute
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AppState, get_app_state, get_current_user, get_db
from app.models.entities import AttendanceEvent, CameraDevice, Employee

router = APIRouter(prefix="/api/v1/overview", tags=["overview"], route_class=FinalizingAPIRoute)


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
    active = [c for c in cams if not getattr(c, "archived", False)]
    live_ready = 0
    mock_cfg = 0
    enabled_real = 0
    if state.camera_registry is not None:
        try:
            health_map = state.camera_registry.health()
            for src in (health_map.get("sources") or []):
                if (
                    str(src.get("provenance") or "") == "CAMERA_LIVE"
                    and src.get("operationally_ready")
                    and str(src.get("decoder_status") or "") == "OK"
                ):
                    live_ready += 1
        except Exception:  # noqa: BLE001
            pass
    for c in active:
        if c.mock_mode:
            mock_cfg += 1
        elif c.enabled:
            enabled_real += 1

    # Honest fleet aggregation — never call the fleet LIVE because of provenance alone (P1-03)
    if not active:
        cam_status_vi = "Chưa cấu hình"
    elif live_ready > 0 and mock_cfg > 0:
        cam_status_vi = f"LIVE sẵn sàng: {live_ready} · MOCK cấu hình: {mock_cfg}"
    elif live_ready > 0:
        cam_status_vi = f"LIVE sẵn sàng: {live_ready} camera (chưa CAMERA_LAB_PASS)"
    elif mock_cfg and not enabled_real:
        cam_status_vi = "Chỉ cấu hình MOCK — chưa có LIVE đã giải mã"
    elif enabled_real:
        cam_status_vi = "Đã cấu hình — chờ LIVE decode / Kiểm tra"
    else:
        cam_status_vi = "Chưa cấu hình"

    return {
        "work_date": wd.isoformat(),
        "camera_status_vi": cam_status_vi,
        "camera_note_vi": "Không thể kết luận vắng mặt khi camera mất kết nối",
        "camera_fleet": {
            "total": len(active),
            "mock_configured": mock_cfg,
            "enabled_non_mock": enabled_real,
            "live_operationally_ready": live_ready,
            "camera_lab_pass": False,
        },
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

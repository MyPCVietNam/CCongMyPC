"""Attendance query and gated mock observation ingest."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    AppState,
    get_app_state,
    get_current_user,
    get_db,
    require_csrf,
    require_permission,
)
from app.core.clock import ensure_utc
from app.core.permissions import DEMO_MOCK_INGEST
from app.models.entities import AttendanceEvent, Employee, User

router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"])


class MockObservationIn(BaseModel):
    employee_id: int
    work_date: date
    observed_at: datetime = Field(description="Timezone-aware ISO datetime")
    quality: float = 1.0
    confidence: float = 1.0
    ambiguous: bool = False
    client_event_id: str | None = Field(
        default=None, description="Optional idempotency key from client"
    )


@router.get("/daily")
def daily(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    work_date: date = Query(...),
) -> dict:
    employees = db.scalars(select(Employee).where(Employee.active.is_(True))).all()
    events = db.scalars(
        select(AttendanceEvent).where(AttendanceEvent.work_date == work_date)
    ).all()
    by_emp: dict[int, list[AttendanceEvent]] = {}
    for e in events:
        by_emp.setdefault(e.employee_id, []).append(e)

    rows = []
    for emp in employees:
        evs = by_emp.get(emp.id, [])
        morning = next((e for e in evs if e.event_type == "MORNING_CHECK_IN"), None)
        afternoon = next((e for e in evs if e.event_type == "AFTERNOON_REFERENCE"), None)
        rows.append(
            {
                "employee_id": emp.id,
                "code": emp.code,
                "full_name": emp.full_name,
                "department": emp.department,
                "morning": _event_brief(morning),
                "afternoon": _afternoon_brief(afternoon),
            }
        )
    return {
        "work_date": work_date.isoformat(),
        "labels_vi": {
            "afternoon_reference": "Giờ nhận diện chiều",
            "photo": "Ảnh đại diện lúc",
            "first_seen": "Lần đầu xuất hiện chiều",
            "anchor": "Mốc kết thúc ca 18:00",
            "verified_exit": "Giờ ra về đã xác minh",
            "last_seen": "Lần cuối xuất hiện",
        },
        "rows": rows,
    }


@router.get("/{employee_id}/afternoon-reference")
def afternoon_reference(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    work_date: date = Query(...),
) -> dict:
    ev = db.scalar(
        select(AttendanceEvent).where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.work_date == work_date,
            AttendanceEvent.event_type == "AFTERNOON_REFERENCE",
        )
    )
    if ev is None:
        return {
            "employee_id": employee_id,
            "work_date": work_date.isoformat(),
            "afternoon_reference_observed_at": None,
            "message_vi": "Chưa có nhận diện chiều",
        }
    return _afternoon_brief(ev) | {"employee_id": employee_id, "work_date": work_date.isoformat()}


@router.get("/{employee_id}/timeline")
def timeline(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    work_date: date = Query(...),
) -> dict:
    evs = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.work_date == work_date,
        )
        .order_by(AttendanceEvent.id)
    ).all()
    return {
        "employee_id": employee_id,
        "work_date": work_date.isoformat(),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "observed_at_utc": e.observed_at_utc.isoformat() if e.observed_at_utc else None,
                "status": e.status,
                "selection_status": e.selection_status,
                "note_vi": e.note_vi,
                "late_seconds": e.late_seconds,
                "review_required": e.review_required,
                "source": e.source,
            }
            for e in evs
        ],
    }


@router.post("/mock-observation", dependencies=[Depends(require_csrf)])
def mock_observation(
    body: MockObservationIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(DEMO_MOCK_INGEST))],
) -> dict:
    """
    Synthetic observation ingest — blocked in production unless demo_mode/allow_mock_observation.
    Requires DEMO_MOCK_INGEST permission. Never creates REAL_CAMERA sourced events.
    """
    if not state.settings.mock_ingest_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                "Endpoint mô phỏng bị tắt ở môi trường production. "
                "Bật MYPC_DEMO_MODE / MYPC_ALLOW_MOCK_OBSERVATION chỉ cho demo tách biệt."
            ),
        )
    emp = db.get(Employee, body.employee_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    if body.observed_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="observed_at phải có múi giờ")

    obs_key = body.client_event_id or _demo_idempotency_key(
        body.employee_id, body.observed_at, body.work_date
    )
    result = state.attendance_service.ingest_face_observation(
        db,
        state.config_service.active,
        employee_id=body.employee_id,
        work_date=body.work_date,
        observed_at_utc=body.observed_at,
        observation_id=obs_key,
        quality=body.quality,
        confidence=body.confidence,
        source="MOCK",
        ambiguous=body.ambiguous,
        idempotency_key=obs_key,
        allow_mock_source=True,
    )
    result["indicator_vi"] = "Dữ liệu mô phỏng"
    result["source"] = "MOCK"
    result["demo_namespace"] = True
    return result


def _demo_idempotency_key(employee_id: int, observed_at: datetime, work_date: date) -> str:
    raw = f"MOCK|{employee_id}|{work_date.isoformat()}|{ensure_utc(observed_at).isoformat()}"
    return "mock-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _iso_utc(dt) -> str | None:
    if dt is None:
        return None
    return ensure_utc(dt).isoformat()


def _event_brief(e: AttendanceEvent | None) -> dict | None:
    if e is None:
        return None
    return {
        "observed_at_utc": _iso_utc(e.observed_at_utc),
        "status": e.status,
        "late_seconds": e.late_seconds,
        "note_vi": e.note_vi,
        "source": e.source,
    }


def _afternoon_brief(e: AttendanceEvent | None) -> dict | None:
    if e is None:
        return None
    return {
        "afternoon_reference_observed_at": _iso_utc(e.observed_at_utc),
        "afternoon_first_observed_at": _iso_utc(e.first_observed_at_utc),
        "afternoon_primary_photo_captured_at": _iso_utc(e.photo_captured_at_utc),
        "selection_status": e.selection_status,
        "selection_policy_version": e.selection_policy_version,
        "review_required": e.review_required,
        "note_vi": e.note_vi,
        "status": e.status,
        "source": e.source,
    }

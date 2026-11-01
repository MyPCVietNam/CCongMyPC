"""P01.5 guided auto-enrollment API — full-frame, no mandatory ROI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AppState, get_app_state, get_db, require_csrf, require_permission
from app.api.enrollment import _decode_image_or_fixture
from app.core.permissions import ENROLLMENT_MANAGE
from app.models.entities import User
from app.services.enrollment_service import _fixture_canvas

router = APIRouter(tags=["auto-enrollment"])


class AutoStartIn(BaseModel):
    authorization_ref: str = Field(min_length=1, max_length=255)
    authorization_ack_vi: str = Field(min_length=8, max_length=4000)
    source: str = Field(default="DEMO", pattern="^(DEMO|UPLOAD|REAL_CAMERA)$")


class FrameIn(BaseModel):
    image_base64: str | None = None
    identity_fixture_key: str | None = None
    force_slot: str | None = None
    declare_body_geometry_blocked: bool = False


class RetryIn(BaseModel):
    slot: str | None = None


class ValidateIn(BaseModel):
    image_base64: str | None = None
    identity_fixture_key: str | None = None


def _svc(state: AppState):
    if state.auto_enrollment_service is None:
        raise HTTPException(status_code=503, detail="Dịch vụ đăng ký tự động chưa sẵn sàng")
    return state.auto_enrollment_service


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/start",
    dependencies=[Depends(require_csrf)],
)
def auto_start(
    employee_id: int,
    body: AutoStartIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    if body.source == "REAL_CAMERA":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAMERA_LAB_BLOCKED",
                "message_vi": (
                    "Đăng ký tự động từ camera thật chưa mở — CAMERA_LAB_PASS chưa đạt."
                ),
            },
        )
    svc = _svc(state)
    try:
        row = svc.start(
            db,
            employee_id=employee_id,
            operator=user.username,
            authorization_ref=body.authorization_ref,
            authorization_ack_vi=body.authorization_ack_vi,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = svc.session_payload(row)
    payload["message_vi"] = (
        "Đã bắt đầu đăng ký tự động. Hệ thống quét toàn khung hình — "
        "không cần vẽ vùng ROI. Làm lần lượt 3 tư thế mặt và 4 ảnh toàn thân."
    )
    return payload


@router.get("/api/v1/employees/{employee_id}/enrollment/auto/{session_id}")
def auto_get(
    employee_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên đăng ký tự động")
    return svc.session_payload(row)


@router.get("/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/events")
def auto_events(
    employee_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    """Polling-friendly event snapshot (SSE/WebSocket can wrap later)."""
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    import json

    progress = json.loads(row.progress_json or "{}")
    return {
        "session_id": session_id,
        "ui_state": row.ui_state,
        "status": row.status,
        "current_step": row.current_step,
        "guidance_vi": row.guidance_vi,
        "announcements": progress.get("announcements", [])[-10:],
        "completed_slots": progress.get("completed_slots", []),
    }


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/frame",
    dependencies=[Depends(require_csrf)],
)
def auto_frame(
    employee_id: int,
    session_id: str,
    body: FrameIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    img = _decode_image_or_fixture(body.image_base64, identity_fixture_key=body.identity_fixture_key)
    try:
        return svc.ingest_frame(
            db,
            session_id,
            img,
            identity_fixture_key=body.identity_fixture_key,
            force_slot=body.force_slot,
            declare_body_geometry_blocked=body.declare_body_geometry_blocked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/pause",
    dependencies=[Depends(require_csrf)],
)
def auto_pause(
    employee_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    try:
        row = svc.pause(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.session_payload(row)


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/resume",
    dependencies=[Depends(require_csrf)],
)
def auto_resume(
    employee_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    try:
        row = svc.resume(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.session_payload(row)


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/retry-step",
    dependencies=[Depends(require_csrf)],
)
def auto_retry(
    employee_id: int,
    session_id: str,
    body: RetryIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    try:
        row = svc.retry_step(db, session_id, slot=body.slot)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.session_payload(row)


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/validate",
    dependencies=[Depends(require_csrf)],
)
@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/activate",
    dependencies=[Depends(require_csrf)],
)
def auto_activate(
    employee_id: int,
    session_id: str,
    body: ValidateIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    verification_image = None
    if body.image_base64:
        verification_image = _decode_image_or_fixture(body.image_base64)
    elif body.identity_fixture_key:
        verification_image = _fixture_canvas(body.identity_fixture_key)
    try:
        return svc.validate_and_activate(
            db,
            session_id,
            actor=user.username,
            identity_fixture_key=body.identity_fixture_key,
            verification_image=verification_image,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/cancel",
    dependencies=[Depends(require_csrf)],
)
def auto_cancel(
    employee_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    try:
        row = svc.cancel(db, session_id, actor=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.session_payload(row)

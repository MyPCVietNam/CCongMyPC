"""P01.5-HF guided auto-enrollment API — fixtures rejected in production."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
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
    camera_id: int | None = None  # required for REAL_CAMERA registry binding


class FrameIn(BaseModel):
    image_base64: str | None = None
    identity_fixture_key: str | None = None
    force_slot: str | None = None
    declare_body_geometry_blocked: bool = False
    camera_id: int | None = None  # when set, server pulls LIVE frame (ignores client base64 as LIVE)


class RetryIn(BaseModel):
    slot: str | None = None


class ValidateIn(BaseModel):
    image_base64: str | None = None
    identity_fixture_key: str | None = None


def _svc(state: AppState):
    if state.auto_enrollment_service is None:
        raise HTTPException(status_code=503, detail="Dịch vụ đăng ký tự động chưa sẵn sàng")
    return state.auto_enrollment_service


def _reject_synthetic_if_needed(state: AppState, body_fixture: str | None, force_slot: str | None = None) -> None:
    settings = state.settings
    if body_fixture and not settings.synthetic_fixtures_allowed():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SYNTHETIC_FIXTURE_DENIED",
                "message_vi": (
                    "Không được dùng identity_fixture_key trên môi trường production. "
                    "Chỉ chấp nhận ảnh thật hoặc upload được ủy quyền."
                ),
            },
        )
    if force_slot and not settings.force_slot_allowed():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORCE_SLOT_DENIED",
                "message_vi": "force_slot chỉ dành cho môi trường kiểm thử tường minh.",
            },
        )


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
        from app.services.pilot_approval import verify_active_approval

        # LIVE connectivity ≠ CAMERA_LAB_PASS. Require signed CAMERA_LAB (+ staging flag) or settings.
        approval = verify_active_approval(
            db, secret_key=state.settings.secret_key, kind="CAMERA_LAB"
        )
        allowed = bool(state.settings.camera_lab_pass) or (
            bool(state.settings.allow_live_enrollment_staging) and approval is not None
        )
        if not allowed:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "CAMERA_LAB_BLOCKED",
                    "message_vi": (
                        "Đăng ký tự động từ camera thật chưa mở — cần CAMERA_LAB_PASS "
                        "hoặc phê duyệt server đã ký + staging. "
                        "Kết nối LIVE chỉ là điều kiện cần, không phải phê duyệt pilot."
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
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    import json

    from app.services.progress_sanitize import scrub_progress

    progress = scrub_progress(json.loads(row.progress_json or "{}"))
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
    _reject_synthetic_if_needed(state, body.identity_fixture_key, body.force_slot)
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    # REAL_CAMERA / registry path: never treat client image_base64 as verified LIVE
    if body.camera_id is not None or (row.source or "").upper() in {"REAL_CAMERA", "CAMERA_LIVE", "LIVE"}:
        from app.vision.camera.registry import FrameAccessError

        cam_id = body.camera_id
        if cam_id is None:
            raise HTTPException(
                status_code=422,
                detail="REAL_CAMERA yêu cầu camera_id — lấy khung từ registry, không từ ảnh client.",
            )
        reg = state.camera_registry
        if reg is None:
            raise HTTPException(status_code=503, detail="Registry camera chưa sẵn sàng")
        try:
            _bound, fr = reg.get_frame(
                int(cam_id),
                require_live=True,
                for_biometric=True,
                allow_stale=False,
                max_age_s=3.0,
            )
        except FrameAccessError as exc:
            raise HTTPException(
                status_code=503, detail={"code": exc.code, "message_vi": exc.message_vi}
            ) from exc
        img = fr.clone_pixels()
    else:
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
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "SYNTHETIC_FIXTURE_DENIED", "message_vi": str(exc)},
        ) from exc
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
    _reject_synthetic_if_needed(state, body.identity_fixture_key)
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    verification_image = None
    if body.image_base64:
        verification_image = _decode_image_or_fixture(body.image_base64)
    elif body.identity_fixture_key:
        verification_image = _fixture_canvas(body.identity_fixture_key + "::verify")
    try:
        return svc.validate_and_activate(
            db,
            session_id,
            actor=user.username,
            identity_fixture_key=body.identity_fixture_key,
            verification_image=verification_image,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "SYNTHETIC_FIXTURE_DENIED", "message_vi": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/api/v1/employees/{employee_id}/enrollment/auto/{session_id}/samples/{sample_uid}/image",
)
def auto_sample_image(
    employee_id: int,
    session_id: str,
    sample_uid: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> Response:
    """Authorized preview of encrypted face crop / body reference — ENROLLMENT_MANAGE only."""
    svc = _svc(state)
    row = svc.get(db, session_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên")
    try:
        samp, plain = svc.get_sample_image(db, session_id, sample_uid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media = "image/jpeg" if plain[:3] == b"\xff\xd8\xff" else "image/png"
    return Response(
        content=plain,
        media_type=media,
        headers={"Cache-Control": "no-store", "X-Sample-Slot": samp.slot, "X-Sample-Kind": samp.kind},
    )


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

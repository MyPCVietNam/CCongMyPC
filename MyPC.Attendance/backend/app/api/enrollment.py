"""Face enrollment / verification API (P01)."""

from __future__ import annotations

import base64
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
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
from app.core.permissions import BIOMETRIC_READ, ENROLLMENT_MANAGE
from app.models.biometric import BiometricEnrollment
from app.models.entities import User
from app.vision.faces.types import MatchOutcome

router = APIRouter(tags=["enrollment"])


class EnrollmentStartIn(BaseModel):
    employee_id: int
    authorization_ref: str = Field(min_length=1, max_length=255)
    authorization_ack_vi: str = Field(min_length=8, max_length=4000)
    source: str = Field(default="DEMO", pattern="^(DEMO|UPLOAD|REAL_CAMERA)$")


class SampleIn(BaseModel):
    """PNG/JPEG base64 or synthetic identity fixture key for CI."""

    image_base64: str | None = None
    identity_fixture_key: str | None = Field(
        default=None,
        description="Synthetic identity key for MOCK_REPLAY tests only",
    )


class VerifyIn(BaseModel):
    image_base64: str | None = None
    identity_fixture_key: str | None = None
    publish_attendance: bool = False


def _decode_image(b64: str | None) -> np.ndarray:
    if not b64:
        # 64x64 gray fixture image
        return np.full((64, 64, 3), 120, dtype=np.uint8)
    raw = base64.b64decode(b64)
    try:
        import cv2  # type: ignore

        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("decode failed")
        return img
    except Exception:
        # Fallback: interpret as synthetic solid image seeded by hash length
        return np.full((64, 64, 3), min(255, 40 + (len(raw) % 200)), dtype=np.uint8)


@router.get("/api/v1/face/status")
def face_status(
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    if state.face_pipeline is None:
        return {"ready": False, "message_vi": "Pipeline khuôn mặt chưa khởi tạo"}
    st = state.face_pipeline.status()
    return {
        "ready": True,
        "pipeline": st,
        "note_vi": (
            "Chế độ synthetic_fixture chỉ dùng cho kiểm thử/mock — "
            "không phải CAMERA_LAB_PASS / FACE_PILOT_PASS."
            if st["embedder"]["backend"] == "synthetic_fixture"
            else "Model OpenCV Zoo đã sẵn sàng trên máy này."
        ),
    }


@router.post("/api/v1/employees/{employee_id}/enrollment/start", dependencies=[Depends(require_csrf)])
def start_enrollment(
    employee_id: int,
    body: EnrollmentStartIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    if body.employee_id != employee_id:
        raise HTTPException(status_code=422, detail="employee_id không khớp")
    if state.face_pipeline is None or state.enrollment_service is None:
        raise HTTPException(status_code=503, detail="Pipeline khuôn mặt chưa sẵn sàng")
    if body.source == "REAL_CAMERA":
        # Live camera enrollment blocked until CAMERA_LAB_PASS
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAMERA_LAB_BLOCKED",
                "message_vi": (
                    "Đăng ký từ camera thật chưa được mở — CAMERA_LAB_PASS chưa đạt. "
                    "Dùng DEMO/UPLOAD trên môi trường kiểm thử."
                ),
            },
        )
    try:
        enr = state.enrollment_service.start_enrollment(
            db,
            employee_id=employee_id,
            enrolled_by=user.username,
            authorization_ref=body.authorization_ref,
            authorization_ack_vi=body.authorization_ack_vi,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "enrollment_id": enr.id,
        "employee_id": enr.employee_id,
        "template_version": enr.template_version,
        "status": enr.status,
        "source": enr.source,
        "message_vi": "Đã mở phiên đăng ký khuôn mặt. Thu thập 5–10 mẫu đạt chất lượng.",
    }


@router.post(
    "/api/v1/employees/{employee_id}/enrollment/{enrollment_id}/sample",
    dependencies=[Depends(require_csrf)],
)
def add_sample(
    employee_id: int,
    enrollment_id: int,
    body: SampleIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    enr = db.get(BiometricEnrollment, enrollment_id)
    if enr is None or enr.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên đăng ký")
    if state.enrollment_service is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    img = _decode_image(body.image_base64)
    try:
        result = state.enrollment_service.add_sample(
            db,
            enrollment_id=enrollment_id,
            image=img,
            identity_fixture_key=body.identity_fixture_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.delete(
    "/api/v1/employees/{employee_id}/enrollment/{enrollment_id}",
    dependencies=[Depends(require_csrf)],
)
def revoke_enrollment(
    employee_id: int,
    enrollment_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    enr = db.get(BiometricEnrollment, enrollment_id)
    if enr is None or enr.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên đăng ký")
    assert state.enrollment_service is not None
    state.enrollment_service.revoke(
        db, enrollment_id=enrollment_id, actor=user.username, reason="Thu hồi theo yêu cầu"
    )
    return {"ok": True, "message_vi": "Đã thu hồi mẫu sinh trắc học. Lịch sử chấm công vẫn giữ."}


@router.get("/api/v1/employees/{employee_id}/enrollment")
def list_enrollments(
    employee_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(BIOMETRIC_READ))],
) -> list[dict]:
    rows = db.scalars(
        select(BiometricEnrollment)
        .where(BiometricEnrollment.employee_id == employee_id)
        .order_by(BiometricEnrollment.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "sample_count": r.sample_count,
            "template_version": r.template_version,
            "model_id": r.model_id,
            "source": r.source,
            "enrolled_at": r.enrolled_at.isoformat() if r.enrolled_at else None,
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        }
        for r in rows
    ]


@router.post("/api/v1/face/verify", dependencies=[Depends(require_csrf)])
def verify_face(
    body: VerifyIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(ENROLLMENT_MANAGE))],
) -> dict:
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    img = _decode_image(body.image_base64)
    loaded = state.template_store.load_active_templates(db)
    # One representative vector per employee (mean) to avoid self-vs-self AMBIGUOUS
    by_emp: dict[int, list] = {}
    for _, vec, emp_id in loaded:
        by_emp.setdefault(emp_id, []).append(vec)
    gallery = []
    for emp_id, vecs in by_emp.items():
        import numpy as np

        mean = np.mean(np.stack(vecs, axis=0), axis=0)
        n = float(np.linalg.norm(mean)) + 1e-12
        gallery.append((emp_id, (mean / n).astype("float32")))
    result = state.face_pipeline.verify(
        img, gallery, identity_fixture_key=body.identity_fixture_key
    )
    # Never expose raw similarity to unauthorized roles — enrollment operators may see banded status
    payload = {
        "outcome": result.outcome.value,
        "employee_id": result.employee_id,
        "message_vi": result.message_vi,
        "model_id": result.model_id,
        "threshold": result.threshold,
        "quality_ok": result.quality.ok if result.quality else None,
        "face_width_px": result.quality.face_width_px if result.quality else None,
    }
    if body.publish_attendance and result.outcome == MatchOutcome.MATCH and result.employee_id:
        # Only REAL_CAMERA source may publish to production attendance — fixture path blocked
        if body.identity_fixture_key or state.face_pipeline.embedder.info.backend == "synthetic_fixture":
            payload["attendance_published"] = False
            payload["attendance_note_vi"] = (
                "Không đưa kết quả DEMO/synthetic vào sổ chấm công production."
            )
        else:
            payload["attendance_published"] = False
            payload["attendance_note_vi"] = "Xuất bản chấm công thật sẽ nối sau CAMERA_LAB_PASS."
    return payload

"""Camera setup, diagnostics, preview, ROI."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AppState, get_app_state, get_current_user, get_db, require_csrf
from app.core.clock import SystemClock
from app.models.entities import CameraDevice, RecognitionRegion

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])


class CameraIn(BaseModel):
    name: str = "EZVIZ H8 Pro"
    host: str = ""
    model: str = "CS-H8-R100-1J5WKFL"
    firmware: str = ""
    rtsp_url_override: str = ""
    mock_mode: bool = True
    enabled: bool = False
    username: str = ""
    password: str = ""


class RegionIn(BaseModel):
    name: str = "arrival"
    x: float = 0.3
    y: float = 0.05
    w: float = 0.4
    h: float = 0.25


@router.get("")
def list_cameras(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict]:
    rows = db.scalars(select(CameraDevice)).all()
    return [_cam_out(r) for r in rows]


@router.post("", dependencies=[Depends(require_csrf)])
def create_camera(
    body: CameraIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    now = SystemClock().now_utc()
    row = CameraDevice(
        name=body.name,
        host=body.host,
        model=body.model,
        firmware=body.firmware,
        rtsp_url_override=body.rtsp_url_override,
        mock_mode=body.mock_mode,
        enabled=body.enabled,
        created_at=now,
        last_health_status="CHUA_CAU_HINH" if not body.host else "CHO_KIEM_TRA",
    )
    db.add(row)
    db.flush()
    if body.username and body.password:
        ref = state.secrets.put_camera_secret(row.id, body.username, body.password)
        row.secret_ref = ref
    # default ROI
    db.add(
        RecognitionRegion(
            camera_id=row.id,
            name="arrival",
            norm_rect_json=json.dumps({"x": 0.3, "y": 0.05, "w": 0.4, "h": 0.25}),
        )
    )
    db.flush()
    return _cam_out(row)


@router.post("/{camera_id}/diagnostics", dependencies=[Depends(require_csrf)])
def diagnostics(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")

    if row.mock_mode:
        st = state.camera.connect_mock()
        row.last_health_at = SystemClock().now_utc()
        row.last_health_status = "MO_PHONG"
        return {
            "camera_id": row.id,
            "mock": True,
            "fsm": st.fsm.value,
            "indicator_vi": "Dữ liệu mô phỏng",
            "stages": [s.__dict__ for s in st.stages],
            "camera_lab_pass": False,
            "note_vi": "Chế độ mô phỏng — không thay thế kiểm thử camera thật.",
        }

    has_secret = state.secrets.has_secret(row.secret_ref)
    stages = state.camera.run_live_diagnostics(row.host, has_secret)
    row.last_health_at = SystemClock().now_utc()
    row.last_health_status = "CHO_KIEM_TRA_THAT"
    # Redact: never include credentials
    return {
        "camera_id": row.id,
        "mock": False,
        "fsm": state.camera.state.fsm.value,
        "stages": [s.__dict__ for s in stages],
        "camera_lab_pass": False,
        "onvif_listed": True,
        "rtsp_tested": False,
        "note_vi": (
            "Camera nằm trong danh sách ONVIF của hãng, nhưng luồng RTSP "
            "chưa được kiểm chứng trên môi trường hiện tại."
        ),
    }


@router.get("/{camera_id}/preview")
def preview(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if not row.mock_mode and state.camera.state.fsm.value != "STREAMING":
        # Fall back to mock frame with explicit indicator — never silent substitute claim
        frame = state.camera.next_frame_png_base64()
        frame["live"] = False
        frame["indicator_vi"] = "Dữ liệu mô phỏng (camera thật chưa STREAMING)"
        return frame
    if row.mock_mode:
        state.camera.connect_mock()
    frame = state.camera.next_frame_png_base64()
    frame["live"] = False
    return frame


@router.put("/{camera_id}/regions", dependencies=[Depends(require_csrf)])
def put_regions(
    camera_id: int,
    body: RegionIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    region = db.scalar(
        select(RecognitionRegion).where(
            RecognitionRegion.camera_id == camera_id, RecognitionRegion.name == body.name
        )
    )
    payload = json.dumps({"x": body.x, "y": body.y, "w": body.w, "h": body.h})
    if region is None:
        region = RecognitionRegion(camera_id=camera_id, name=body.name, norm_rect_json=payload)
        db.add(region)
    else:
        region.norm_rect_json = payload
        region.calibration_version += 1
        region.exit_calibration_valid = False  # invalidate on ROI change
    db.flush()
    return {
        "ok": True,
        "region": json.loads(region.norm_rect_json),
        "calibration_version": region.calibration_version,
        "exit_calibration_valid": region.exit_calibration_valid,
        "message_vi": "Đã lưu vùng nhận diện — cần hiệu chỉnh lại xác minh ra về",
    }


def _cam_out(r: CameraDevice) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "host": r.host,
        "model": r.model,
        "firmware": r.firmware,
        "has_rtsp_override": bool(r.rtsp_url_override),
        "has_secret": bool(r.secret_ref),
        "mock_mode": r.mock_mode,
        "enabled": r.enabled,
        "last_health_status": r.last_health_status,
        "last_health_at": r.last_health_at.isoformat() if r.last_health_at else None,
    }

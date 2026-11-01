"""Camera setup, diagnostics, preview, ROI — CAMERA_MANAGE + SSRF/ROI guards."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
import math

from pydantic import BaseModel, Field, field_validator
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
from app.core.clock import SystemClock
from app.core.permissions import CAMERA_MANAGE
from app.core.validation import (
    ValidationErrorVi,
    redact_url,
    validate_camera_host,
    validate_roi,
    validate_rtsp_url,
)
from app.models.entities import CameraDevice, RecognitionRegion, User

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

    @field_validator("x", "y", "w", "h")
    @classmethod
    def _finite(cls, v: float) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("Tọa độ ROI không hợp lệ")
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Tọa độ ROI không được NaN/Infinity")
        return float(v)


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
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    try:
        host = validate_camera_host(body.host, allow_empty=True)
        rtsp = validate_rtsp_url(body.rtsp_url_override, allow_empty=True)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = SystemClock().now_utc()
    row = CameraDevice(
        name=body.name,
        host=host,
        model=body.model,
        firmware=body.firmware,
        rtsp_url_override=rtsp,
        mock_mode=body.mock_mode,
        enabled=body.enabled,
        created_at=now,
        last_health_status="CHUA_CAU_HINH" if not host else "CHO_KIEM_TRA",
    )
    db.add(row)
    db.flush()
    if body.username and body.password:
        ref = state.secrets.put_camera_secret(row.id, body.username, body.password)
        row.secret_ref = ref
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
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
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
            "live": False,
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
    return {
        "camera_id": row.id,
        "mock": False,
        "live": False,
        "fsm": state.camera.state.fsm.value,
        "stages": [s.__dict__ for s in stages],
        "camera_lab_pass": False,
        "onvif_listed": True,
        "rtsp_tested": False,
        "rtsp_override_redacted": redact_url(row.rtsp_url_override),
        "note_vi": (
            "Camera nằm trong danh sách ONVIF của hãng, nhưng luồng RTSP "
            "chưa được kiểm chứng trên môi trường hiện tại."
        ),
    }


@router.get("/gateway/health")
def gateway_health(
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """P02 camera gateway health — never claims CAMERA_LAB_PASS without lab evidence."""
    gw = state.camera_gateway
    if gw is None:
        return {
            "ready": False,
            "camera_lab_pass": False,
            "detail_vi": "Gateway chưa khởi tạo.",
            "code": "GATEWAY_NOT_CONFIGURED",
        }
    h = gw.health()
    return {
        "ready": h.decoder_status.value in {"OK", "STALE"},
        "provenance": h.provenance.value,
        "decoder_status": h.decoder_status.value,
        "native_width": h.native_width,
        "native_height": h.native_height,
        "fps_estimate": h.fps_estimate,
        "dropped_frames": h.dropped_frames,
        "stale_frames": h.stale_frames,
        "reconnect_count": h.reconnect_count,
        "last_frame_at": h.last_frame_at.isoformat() if h.last_frame_at else None,
        "detail_vi": h.detail_vi,
        "camera_lab_pass": False,  # hard: only Windows lab evidence may flip this elsewhere
        "extras": {k: v for k, v in (h.extras or {}).items() if "password" not in k.lower()},
    }


@router.post("/gateway/live/configure", dependencies=[Depends(require_csrf)])
def configure_live_gateway(
    body: dict[str, Any],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """
    Configure LiveRTSPGateway from local credentials/URI.
    Password is accepted once, never echoed back. Does NOT set CAMERA_LAB_PASS.
    """
    from app.vision.camera.gateway import LiveRTSPGateway, sanitize_rtsp_for_log

    uri = (body.get("rtsp_uri") or "").strip()
    camera_id = str(body.get("camera_id") or "live-0")
    if not uri:
        raise HTTPException(status_code=422, detail="Thiếu rtsp_uri")
    # Basic SSRF-ish guard: require rtsp/rtsps scheme
    if not uri.lower().startswith(("rtsp://", "rtsps://")):
        raise HTTPException(status_code=422, detail="Chỉ chấp nhận URI rtsp:// hoặc rtsps://")
    if state.camera_gateway is not None:
        try:
            state.camera_gateway.stop()
        except Exception:
            pass
    gw = LiveRTSPGateway(uri, camera_id=camera_id)
    gw.start()
    state.camera_gateway = gw
    return {
        "ok": True,
        "sanitized_uri": sanitize_rtsp_for_log(uri),
        "camera_lab_pass": False,
        "message_vi": (
            "Đã cấu hình gateway LIVE. Trạng thái giải mã xem /gateway/health. "
            "CAMERA_LAB_PASS vẫn BLOCKED cho đến khi lab Windows xác nhận."
        ),
        "operator": user.username,
    }


@router.get("/{camera_id}/preview")
def preview(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """
    Mock cameras return DEMO frames.
    Live cameras return LIVE frame only when actually STREAMING with a real decoder;
    otherwise explicit CAMERA_UNAVAILABLE / LIVE_NOT_IMPLEMENTED — never silent mock substitute.
    """
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")

    if row.mock_mode:
        state.camera.connect_mock()
        frame = state.camera.next_frame_png_base64()
        frame["live"] = False
        frame["source"] = "DEMO"
        frame["indicator_vi"] = "Dữ liệu mô phỏng"
        return frame

    # Live path — do not fall back to mock frames
    live = state.camera.try_live_frame(row.host, row.rtsp_url_override)
    if live is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVE_NOT_IMPLEMENTED",
                "message_vi": (
                    "Camera thật chưa có khung hình LIVE đã giải mã. "
                    "Không thay thế bằng dữ liệu mô phỏng. "
                    "Chạy Kiểm tra kết nối / Windows Camera Lab."
                ),
                "camera_lab_pass": False,
            },
        )
    live["live"] = True
    live["source"] = "REAL_CAMERA"
    live["indicator_vi"] = "CAMERA THẬT (LIVE)"
    return live


@router.put("/{camera_id}/regions", dependencies=[Depends(require_csrf)])
def put_regions(
    camera_id: int,
    body: RegionIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    try:
        rect = validate_roi(body.x, body.y, body.w, body.h)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    region = db.scalar(
        select(RecognitionRegion).where(
            RecognitionRegion.camera_id == camera_id, RecognitionRegion.name == body.name
        )
    )
    payload = json.dumps(rect)
    if region is None:
        region = RecognitionRegion(camera_id=camera_id, name=body.name, norm_rect_json=payload)
        db.add(region)
    else:
        region.norm_rect_json = payload
        region.calibration_version += 1
        region.exit_calibration_valid = False
    db.flush()
    return {
        "ok": True,
        "region": rect,
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
        "rtsp_override_redacted": redact_url(r.rtsp_url_override),
        "has_secret": bool(r.secret_ref),
        "mock_mode": r.mock_mode,
        "enabled": r.enabled,
        "last_health_status": r.last_health_status,
        "last_health_at": r.last_health_at.isoformat() if r.last_health_at else None,
    }

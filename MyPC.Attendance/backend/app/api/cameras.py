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
        "onvif_listed": False,
        "onvif_status": "UNVERIFIED",
        "rtsp_tested": False,
        "rtsp_override_redacted": "REDACTED" if row.rtsp_url_override else "",
        "note_vi": (
            "VENDOR_SPEC: model có thể hỗ trợ ONVIF theo tài liệu hãng — "
            "đây KHÔNG phải kết quả probe/discovery thành công trên máy này. "
            "RTSP decode vẫn chưa được chứng minh (CAMERA_LAB BLOCKED)."
        ),
    }


@router.get("/gateway/health")
def gateway_health(
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    camera_id: int | None = None,
) -> dict:
    """P02-HF registry health — never claims CAMERA_LAB_PASS without lab evidence."""
    reg = state.camera_registry
    if reg is None:
        return {
            "ready": False,
            "camera_lab_pass": False,
            "detail_vi": "Registry camera chưa khởi tạo.",
            "code": "GATEWAY_NOT_CONFIGURED",
        }
    payload = reg.health(camera_id)
    payload["ready"] = any(
        s.get("decoder_status") in {"OK", "STALE"} for s in payload.get("sources", [])
    )
    payload["vendor_spec"] = {
        "model": "CS-H8-R100-1J5WKFL",
        "max_resolution_claimed": "2880x1620",
        "note_vi": "VENDOR_SPEC — chưa phải DECODED_MEASURED trên máy này.",
    }
    return payload


@router.post("/gateway/live/configure", dependencies=[Depends(require_csrf)])
def configure_live_gateway(
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """
    Bind LiveRTSPGateway into per-camera registry.
    Credentials must NOT be in URI (rejected by policy). Does NOT set CAMERA_LAB_PASS.
    """
    from app.core.validation import ValidationErrorVi
    from app.vision.camera.gateway import LiveRTSPGateway, StreamProvenance
    from app.vision.camera.rtsp_policy import diagnostic_rtsp_label, validate_live_rtsp_uri

    uri = (body.get("rtsp_uri") or "").strip()
    camera_db_id = body.get("camera_id")
    profile = str(body.get("profile") or "MAIN")
    if camera_db_id is None:
        raise HTTPException(status_code=422, detail="Thiếu camera_id (DB)")
    try:
        camera_db_id = int(camera_db_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="camera_id không hợp lệ") from exc
    row = db.get(CameraDevice, camera_db_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if not uri:
        raise HTTPException(status_code=422, detail="Thiếu rtsp_uri")
    try:
        endpoint = validate_live_rtsp_uri(uri)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail={"code": "RTSP_POLICY", "message_vi": str(exc)}) from exc
    # Rebuild URI without secrets (already stripped by policy) for OpenCV only in-process
    safe_uri = f"{endpoint.scheme}://{endpoint.host}:{endpoint.port}{endpoint.path}"
    # Optional username/password from body — never echo
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if username or password:
        # Embed only into in-memory capture URI; never return/log
        from urllib.parse import quote

        safe_uri = (
            f"{endpoint.scheme}://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{endpoint.host}:{endpoint.port}{endpoint.path}"
        )
        # Store encrypted via secrets store if available
        try:
            state.secrets.put_camera_secret(camera_db_id, username, password)
        except Exception:
            pass

    if state.camera_registry is None:
        from app.vision.camera.registry import CameraSourceRegistry

        state.camera_registry = CameraSourceRegistry()
    gw = LiveRTSPGateway(safe_uri, camera_id=str(camera_db_id))
    # Bind first so config_revision is synced before any frames are published
    bound = state.camera_registry.bind(
        camera_db_id, gw, provenance=StreamProvenance.CAMERA_LIVE, profile=profile
    )
    gw.start()
    state.camera_gateway = gw  # legacy pointer
    row.mock_mode = False
    return {
        "ok": True,
        "camera_id": camera_db_id,
        "config_revision": bound.config_revision,
        "diagnostic_label": diagnostic_rtsp_label(camera_id=camera_db_id, profile=profile),
        "endpoint": {
            "scheme": endpoint.scheme,
            "host": endpoint.host,
            "port": endpoint.port,
            "path_redacted": True,
        },
        "camera_lab_pass": False,
        "message_vi": (
            "Đã gắn gateway LIVE vào registry theo camera_id. "
            "Preview/enrollment phải dùng cùng nguồn. CAMERA_LAB_PASS vẫn BLOCKED."
        ),
        "operator": user.username,
    }


def _preview_from_frame(fr, *, live: bool, source: str, indicator_vi: str) -> dict:
    import base64

    import cv2

    # Browser preview: resize copy — never mutate sealed original
    pixels = fr.clone_pixels()
    h, w = pixels.shape[:2]
    max_w = 960
    if w > max_w:
        scale = max_w / float(w)
        pixels = cv2.resize(pixels, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", pixels, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise HTTPException(status_code=500, detail="Không mã hóa được preview")
    return {
        "data_base64": base64.b64encode(buf.tobytes()).decode("ascii"),
        "mime": "image/jpeg",
        "indicator_vi": indicator_vi,
        "width": fr.width,
        "height": fr.height,
        "preview_width": pixels.shape[1],
        "preview_height": pixels.shape[0],
        "live": live,
        "source": source,
        "provenance": fr.provenance.value,
        "decoder_status": fr.decoder_status.value,
        "frame_id": fr.frame_id,
        "config_revision": fr.config_revision,
        "clock_trust": fr.clock_trust.value,
        "pixel_sha256": fr.pixel_sha256,
        "size_source": "DECODED_MEASURED",
        "camera_lab_pass": False,
        "mock": source in {"DEMO", "MOCK"},
    }


@router.get("/{camera_id}/preview")
def preview(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """
    Unified preview: mock cameras → MOCK gateway; live → registry LiveRTSPGateway.
    Never silent MOCK substitute for a live-configured camera.
    """
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")

    reg = state.camera_registry
    bound = reg.get(camera_id) if reg is not None else None

    if row.mock_mode and bound is None:
        from app.vision.camera.gateway import MockFrameGateway, StreamProvenance

        if reg is None:
            from app.vision.camera.registry import CameraSourceRegistry

            state.camera_registry = CameraSourceRegistry()
            reg = state.camera_registry
        gw = MockFrameGateway(camera_id=str(camera_id))
        gw.start()
        reg.bind(camera_id, gw, provenance=StreamProvenance.MOCK, profile="MOCK")
        bound = reg.get(camera_id)

    if bound is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVE_NOT_CONFIGURED",
                "message_vi": (
                    "Chưa gắn nguồn LIVE cho camera này. Cấu hình gateway hoặc bật MOCK tường minh. "
                    "Không thay thế bằng khung DEMO ẩn."
                ),
                "camera_lab_pass": False,
            },
        )

    fr = bound.gateway.get_latest_frame()
    if fr is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAMERA_OFFLINE",
                "message_vi": "Chưa có khung hình đã giải mã (CAMERA_OFFLINE / đang kết nối lại).",
                "camera_lab_pass": False,
                "config_revision": bound.config_revision,
            },
        )
    if fr.config_revision and fr.config_revision != bound.config_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_FRAME_REVISION",
                "message_vi": "Khung hình cũ sau khi đổi cấu hình — đã từ chối.",
            },
        )
    live = bound.provenance.value == "CAMERA_LIVE"
    source = "REAL_CAMERA" if live else bound.provenance.value
    indicator = "CAMERA THẬT (LIVE)" if live else (
        "Dữ liệu mô phỏng" if bound.provenance.value == "MOCK" else "Video ghi hình được ủy quyền"
    )
    return _preview_from_frame(fr, live=live, source=source, indicator_vi=indicator)


@router.get("/{camera_id}/quality/diagnostics")
def quality_diagnostics(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    reg = state.camera_registry
    bound = reg.get(camera_id) if reg else None
    h = bound.gateway.health() if bound else None
    fr = bound.gateway.get_latest_frame() if bound else None
    return {
        "camera_id": camera_id,
        "vendor_spec": {
            "model": row.model or "CS-H8-R100-1J5WKFL",
            "max_resolution": "2880x1620",
            "status": "VENDOR_SPEC",
        },
        "onvif_reported": {"status": "UNVERIFIED", "note_vi": "Chưa probe ONVIF an toàn trên máy này."},
        "ffprobe_reported": {"status": "UNVERIFIED"},
        "decoded_measured": {
            "status": "DECODED_MEASURED" if fr else "UNVERIFIED",
            "width": fr.width if fr else None,
            "height": fr.height if fr else None,
            "fps_measured": h.fps_estimate if h else None,
            "overwritten_latest": h.dropped_frames if h else None,
            "decode_errors": getattr(h, "decode_errors", None) if h else None,
            "clock_trust": fr.clock_trust.value if fr else None,
            "frame_id": fr.frame_id if fr else None,
            "pixel_sha256": fr.pixel_sha256 if fr else None,
        },
        "browser_preview": {"note_vi": "Preview đã resize — không dùng làm native gate."},
        "auto_enhance": {
            "requested": "Tự động",
            "effective": "AUTO_TEST_ONLY",
            "note_vi": "Ảnh gốc là quyết định chính thức; enhanced chỉ shadow A/B cho đến khi pilot LIVE phê duyệt.",
        },
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "config_revision": bound.config_revision if bound else None,
        "provenance": bound.provenance.value if bound else None,
    }


@router.post("/{camera_id}/quality/analyze-once", dependencies=[Depends(require_csrf)])
def analyze_once(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Run conservative enhancement on a *copy* of current frame; original hash must stay stable."""
    from app.vision.faces.adaptive_quality import trial_enhance_copy

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    reg = state.camera_registry
    bound = reg.get(camera_id) if reg else None
    if bound is None:
        raise HTTPException(status_code=503, detail="Chưa có nguồn khung hình")
    fr = bound.gateway.get_latest_frame()
    if fr is None:
        raise HTTPException(status_code=503, detail="Chưa có khung hình")
    original_hash = fr.pixel_sha256
    owned = fr.clone_pixels()
    trial = trial_enhance_copy(owned)
    # Prove original sealed buffer unchanged
    import hashlib

    import numpy as np

    still = hashlib.sha256(np.ascontiguousarray(fr.bgr).tobytes()).hexdigest()
    return {
        "original_pixel_sha256": original_hash,
        "original_unchanged": still == original_hash,
        "enhancement_status": trial.status,
        "applied_methods": list(trial.applied_methods),
        "quality_flags": list(trial.quality_flags),
        "processing_ms": trial.processing_ms,
        "effective_mode": "AUTO_TEST_ONLY",
        "note_vi": "Kết quả enhanced chỉ để so sánh bóng — không kích hoạt AUTO_VALIDATED.",
        "camera_lab_pass": False,
    }


def _quality_settings_out(row) -> dict:
    return {
        "camera_id": row.camera_id,
        "revision": row.revision,
        "requested_mode": row.requested_mode,
        "effective_mode": row.effective_mode,
        "model_hash_pin": row.model_hash_pin or None,
        "gallery_revision_pin": row.gallery_revision_pin or None,
        "threshold_id_pin": row.threshold_id_pin or None,
        "validated_at": row.validated_at.isoformat() if row.validated_at else None,
        "validated_by": row.validated_by or None,
        "reverted_reason": row.reverted_reason or None,
        "note_vi": (
            "AUTO_VALIDATED chỉ sau pilot LIVE độc lập + phê duyệt ADMIN. "
            "Mặc định an toàn: AUTO_TEST_ONLY (ảnh gốc chính thức)."
        ),
    }


@router.get("/{camera_id}/quality/settings")
def get_quality_settings(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    from app.models.entities import CameraQualitySettings

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    qs = db.scalar(
        select(CameraQualitySettings).where(CameraQualitySettings.camera_id == camera_id)
    )
    if qs is None:
        return {
            "camera_id": camera_id,
            "revision": 0,
            "requested_mode": "AUTO",
            "effective_mode": "AUTO_TEST_ONLY",
            "note_vi": "Chưa lưu — dùng mặc định AUTO_TEST_ONLY.",
        }
    return _quality_settings_out(qs)


@router.put("/{camera_id}/quality/settings", dependencies=[Depends(require_csrf)])
def put_quality_settings(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Transactional settings apply. Never silently promotes to AUTO_VALIDATED."""
    from app.models.entities import CameraQualitySettings
    from app.vision.faces.adaptive_quality import effective_auto_mode

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    requested = str(body.get("requested_mode") or "AUTO")
    force_revert = bool(body.get("revert"))
    # Explicit validated=True in body alone is insufficient — require prior pin + admin flag
    allow_validated = bool(body.get("admin_confirm_live_pilot")) and bool(
        body.get("model_hash_pin") and body.get("gallery_revision_pin") and body.get("threshold_id_pin")
    )
    mode = effective_auto_mode(
        requested, validated=allow_validated and not force_revert, reverted=force_revert
    )
    if mode.value == "AUTO_VALIDATED" and not allow_validated:
        mode = effective_auto_mode("AUTO", validated=False)
    qs = db.scalar(
        select(CameraQualitySettings).where(CameraQualitySettings.camera_id == camera_id)
    )
    now = SystemClock().now_utc()
    if qs is None:
        qs = CameraQualitySettings(camera_id=camera_id, revision=1)
        db.add(qs)
    else:
        qs.revision += 1
    qs.requested_mode = requested
    qs.effective_mode = mode.value
    qs.model_hash_pin = str(body.get("model_hash_pin") or qs.model_hash_pin or "")
    qs.gallery_revision_pin = str(body.get("gallery_revision_pin") or qs.gallery_revision_pin or "")
    qs.threshold_id_pin = str(body.get("threshold_id_pin") or qs.threshold_id_pin or "")
    if force_revert:
        qs.reverted_reason = str(body.get("reverted_reason") or "OPERATOR_ROLLBACK")
        qs.validated_at = None
        qs.validated_by = ""
    elif mode.value == "AUTO_VALIDATED":
        qs.validated_at = now
        qs.validated_by = user.username
        qs.reverted_reason = ""
    qs.updated_at = now
    qs.payload_json = json.dumps(
        {"actor": user.username, "requested": requested, "effective": mode.value},
        ensure_ascii=False,
    )
    db.flush()
    return _quality_settings_out(qs)


@router.post("/{camera_id}/quality/evaluation/run", dependencies=[Depends(require_csrf)])
def run_ab_evaluation(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Offline paired A/B aggregate — NEVER sets can_auto_enable from CSV alone."""
    import uuid

    from app.models.entities import AbEvaluationRun
    from app.vision.faces.paired_ab import EvaluationInputError, evaluate_pairs

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    pairs = body.get("pairs") or []
    if not isinstance(pairs, list):
        raise HTTPException(status_code=422, detail="pairs phải là danh sách")
    try:
        result = evaluate_pairs(pairs)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_id = str(uuid.uuid4())
    now = SystemClock().now_utc()
    db.add(
        AbEvaluationRun(
            camera_id=camera_id,
            run_id=run_id,
            source_mix=",".join(sorted((result.get("by_source") or {}).keys())) or "EMPTY",
            sample_count=int(result.get("samples") or 0),
            metrics_json=json.dumps(
                {k: result[k] for k in ("original", "enhanced", "paired", "latency_ms") if k in result},
                ensure_ascii=False,
            ),
            blockers_json=json.dumps(result.get("blockers") or [], ensure_ascii=False),
            can_auto_enable=False,  # hard rule
            approval_status="PENDING",
            created_at=now,
            note_vi="Chỉ aggregate đã ẩn danh — không lưu ảnh khuôn mặt.",
        )
    )
    db.flush()
    return {
        "run_id": run_id,
        "camera_id": camera_id,
        "result": result,
        "can_auto_enable_enhancement": False,
        "operator": user.username,
        "note_vi": "Kết quả offline không đủ để bật AUTO_VALIDATED.",
    }


@router.get("/{camera_id}/quality/report")
def redacted_quality_report(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """Export-safe report: camera_id/profile/status only — no URI, faces, embeddings."""
    from app.models.entities import AbEvaluationRun, CameraQualitySettings
    from app.vision.camera.rtsp_policy import diagnostic_rtsp_label

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    qs = db.scalar(
        select(CameraQualitySettings).where(CameraQualitySettings.camera_id == camera_id)
    )
    runs = db.scalars(
        select(AbEvaluationRun)
        .where(AbEvaluationRun.camera_id == camera_id)
        .order_by(AbEvaluationRun.id.desc())
        .limit(5)
    ).all()
    reg = state.camera_registry
    bound = reg.get(camera_id) if reg else None
    h = bound.gateway.health() if bound else None
    return {
        "camera_id": camera_id,
        "diagnostic_label": diagnostic_rtsp_label(
            camera_id=camera_id, profile=bound.profile if bound else "UNKNOWN"
        ),
        "provenance": bound.provenance.value if bound else None,
        "decoder_status": h.decoder_status.value if h else "NOT_CONFIGURED",
        "decoded_measured": {
            "width": h.native_width if h else None,
            "height": h.native_height if h else None,
            "fps_measured": h.fps_estimate if h else None,
        },
        "effective_mode": qs.effective_mode if qs else "AUTO_TEST_ONLY",
        "recent_ab_runs": [
            {
                "run_id": r.run_id,
                "sample_count": r.sample_count,
                "source_mix": r.source_mix,
                "can_auto_enable": False,
                "approval_status": r.approval_status,
                "blockers": json.loads(r.blockers_json or "[]"),
            }
            for r in runs
        ],
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "secrets_present": False,
        "note_vi": "Báo cáo đã ẩn URI/mật khẩu/ảnh khuôn mặt/embeddings.",
    }


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

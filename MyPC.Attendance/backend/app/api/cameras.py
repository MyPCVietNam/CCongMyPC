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
    """Registry health — ready≠STALE; never claims CAMERA_LAB_PASS without signed lab evidence."""
    reg = state.camera_registry
    if reg is None:
        return {
            "ready": False,
            "camera_lab_pass": False,
            "detail_vi": "Registry camera chưa khởi tạo.",
            "code": "GATEWAY_NOT_CONFIGURED",
        }
    payload = reg.health(camera_id)
    # Settings flag ≠ signed physical CAMERA_LAB evidence
    payload["settings_flag_camera_lab"] = bool(state.settings.camera_lab_pass)
    payload["camera_lab_pass"] = False  # never claim PASS from config alone
    payload["signed_camera_lab"] = False
    if camera_id is not None and state.face_pipeline is not None and state.template_store is not None:
        try:
            from app.services.pilot_approval import verify_active_approval
            from app.services.server_pins import derive_live_pins

            with state.session_factory() as sdb:
                pins, _ = derive_live_pins(
                    sdb, pipeline=state.face_pipeline, store=state.template_store
                )
                view = verify_active_approval(
                    sdb,
                    secret_key=state.settings.secret_key,
                    kind="CAMERA_LAB",
                    camera_id=int(camera_id),
                    model_hash_pin=pins["model_hash_pin"],
                    gallery_revision_pin=pins["gallery_revision_pin"],
                    threshold_id_pin=pins["threshold_id_pin"],
                )
                payload["signed_camera_lab"] = bool(view and view.valid)
        except Exception:
            payload["signed_camera_lab"] = False
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

    from app.vision.camera.rtsp_policy import pinned_rtsp_authority

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
        # IPv4 literal only by default — pin destination before OpenCV opens
        endpoint = validate_live_rtsp_uri(uri, require_ipv4_literal=True)
        pinned_host = pinned_rtsp_authority(endpoint)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail={"code": "RTSP_POLICY", "message_vi": str(exc)}) from exc
    # Rebuild capture URI with pinned IPv4 (never re-resolve hostname in FFmpeg)
    safe_uri = f"{endpoint.scheme}://{pinned_host}:{endpoint.port}{endpoint.path}"
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    secret_ref = row.secret_ref or ""
    if username or password:
        from urllib.parse import quote

        try:
            # Single atomic secret write — persist ref once
            secret_ref = state.secrets.put_camera_secret(camera_db_id, username, password)
            row.secret_ref = secret_ref
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "SECRET_STORE_FAILED",
                    "message_vi": "Không lưu được credential camera — từ chối gắn LIVE không an toàn.",
                },
            ) from exc
        safe_uri = (
            f"{endpoint.scheme}://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{pinned_host}:{endpoint.port}{endpoint.path}"
        )
    else:
        stored = state.secrets.get_camera_secret(secret_ref) if secret_ref else None
        if stored and stored.get("username"):
            from urllib.parse import quote

            safe_uri = (
                f"{endpoint.scheme}://{quote(stored['username'], safe='')}:{quote(stored.get('password') or '', safe='')}"
                f"@{pinned_host}:{endpoint.port}{endpoint.path}"
            )

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
    from app.models.entities import CameraLiveBinding
    from app.services.pilot_approval import revoke_approvals

    binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_db_id))
    now = SystemClock().now_utc()
    if binding is None:
        binding = CameraLiveBinding(camera_id=camera_db_id)
        db.add(binding)
    else:
        # Profile/config change invalidates prior signed approvals for this camera
        if binding.config_revision and binding.config_revision != bound.config_revision:
            revoke_approvals(
                db, camera_id=camera_db_id, reason="CAMERA_CONFIG_REVISION_CHANGED"
            )
    binding.scheme = endpoint.scheme
    binding.host = pinned_host  # persist pinned IP, not unresolved hostname
    binding.port = endpoint.port
    binding.path = endpoint.path
    binding.profile = profile
    binding.resolved_ips_json = json.dumps(list(endpoint.resolved_ips))
    binding.config_revision = bound.config_revision
    binding.enabled = True
    binding.updated_at = now
    return {
        "ok": True,
        "camera_id": camera_db_id,
        "config_revision": bound.config_revision,
        "diagnostic_label": diagnostic_rtsp_label(camera_id=camera_db_id, profile=profile),
        "endpoint": {
            "scheme": endpoint.scheme,
            "host": pinned_host,
            "port": endpoint.port,
            "path_redacted": True,
            "resolved_ip_count": len(endpoint.resolved_ips),
            "destination_pinned": True,
        },
        "camera_lab_pass": False,
        "message_vi": (
            "Đã gắn gateway LIVE (IPv4 đã ghim) vào registry theo camera_id. "
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

    from app.vision.camera.registry import FrameAccessError

    try:
        bound, fr = reg.get_frame(
            camera_id,
            allow_mock=bound.provenance.value == "MOCK",
            allow_recorded=bound.provenance.value == "AUTHORIZED_RECORDED",
            allow_stale=True,  # preview may show STALE with watermark
            max_age_s=30.0,
            for_biometric=False,
        )
    except FrameAccessError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": exc.code,
                "message_vi": exc.message_vi,
                "camera_lab_pass": False,
                "config_revision": bound.config_revision if bound else None,
            },
        ) from exc
    live = bound.provenance.value == "CAMERA_LIVE"
    source = "REAL_CAMERA" if live else bound.provenance.value
    stale = fr.decoder_status.value == "STALE"
    indicator = "CAMERA THẬT (LIVE)" if live else (
        "Dữ liệu mô phỏng" if bound.provenance.value == "MOCK" else "Video ghi hình được ủy quyền"
    )
    if stale:
        indicator = f"{indicator} — STALE (chỉ xem, không nhận diện)"
    out = _preview_from_frame(fr, live=live and not stale, source=source, indicator_vi=indicator)
    out["stale"] = stale
    out["operationally_ready"] = live and not stale and fr.decoder_status.value == "OK"
    return out


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
    from app.models.entities import CameraQualitySettings

    reg = state.camera_registry
    bound = reg.get(camera_id) if reg else None
    h = bound.gateway.health() if bound else None
    fr = bound.gateway.get_latest_frame() if bound else None
    qs = db.scalar(select(CameraQualitySettings).where(CameraQualitySettings.camera_id == camera_id))
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
            "operationally_ready": bool(getattr(h, "operationally_ready", False)) if h else False,
        },
        "browser_preview": {"note_vi": "Preview đã resize — không dùng làm native gate."},
        "auto_enhance": {
            "requested": qs.requested_mode if qs else "AUTO",
            "effective": qs.effective_mode if qs else "AUTO_TEST_ONLY",
            "reverted_reason": qs.reverted_reason if qs else None,
            "note_vi": "Ảnh gốc là quyết định chính thức; enhanced chỉ shadow A/B cho đến khi có phê duyệt server đã ký.",
        },
        "camera_lab_pass": bool(state.settings.camera_lab_pass),
        "face_pilot_pass": bool(state.settings.face_pilot_pass),
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
    """Paired ORIGINAL vs ENHANCED recognition on registry frame copy; original bytes immutable."""
    from app.vision.camera.registry import FrameAccessError
    from app.vision.faces.paired_inference import run_paired_recognition

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    reg = state.camera_registry
    if reg is None:
        raise HTTPException(status_code=503, detail="Chưa có nguồn khung hình")
    bound0 = reg.get(camera_id)
    try:
        bound, fr = reg.get_frame(
            camera_id,
            allow_mock=bool(bound0 and bound0.provenance.value == "MOCK"),
            allow_recorded=True,
            allow_stale=False,
            for_biometric=False,
            max_age_s=5.0,
        )
    except FrameAccessError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message_vi": exc.message_vi}) from exc
    from app.services.gallery_loader import load_active_gallery

    original_hash = fr.pixel_sha256
    owned = fr.clone_pixels()
    gallery_snap = (
        load_active_gallery(db, state.template_store)
        if state.template_store is not None
        else None
    )
    gallery = list(gallery_snap.pairs) if gallery_snap else []
    paired = run_paired_recognition(owned, pipeline=state.face_pipeline, gallery=gallery)
    still = fr.pixel_sha256
    return {
        "original_pixel_sha256": original_hash,
        "original_unchanged": still == original_hash,
        "paired": paired,
        "gallery_status": gallery_snap.status if gallery_snap else "BLOCKED_GALLERY",
        "gallery_count": gallery_snap.count if gallery_snap else 0,
        "gallery_revision": gallery_snap.revision if gallery_snap else "EMPTY",
        "enhancement_status": paired.get("enhancement_status"),
        "applied_methods": paired.get("applied_methods") or [],
        "effective_mode": "AUTO_TEST_ONLY",
        "note_vi": paired.get("note_vi")
        or "So sánh nhận diện gốc/xử lý (shadow) — không kích hoạt AUTO_VALIDATED.",
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
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Transactional settings apply. Never silently promotes to AUTO_VALIDATED."""
    from app.models.entities import CameraQualitySettings
    from app.vision.faces.adaptive_quality import effective_auto_mode
    from app.services.pilot_approval import revoke_approvals, verify_active_approval

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")

    from app.services.server_pins import derive_live_pins

    requested = str(body.get("requested_mode") or "AUTO")
    force_revert = bool(body.get("revert"))
    # JSON-only admin_confirm_live_pilot is REJECTED — require HMAC-signed server approval
    if body.get("admin_confirm_live_pilot"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNSIGNED_APPROVAL_REJECTED",
                "message_vi": (
                    "Không thể bật AUTO_VALIDATED bằng cờ JSON. "
                    "Cần bản ghi phê duyệt server đã ký (PILOT_APPROVE)."
                ),
            },
        )
    # Server-derived pins only — client hashes are never trusted for promotion
    server_pins: dict[str, str] = {"model_hash_pin": "", "gallery_revision_pin": "", "threshold_id_pin": ""}
    if state.face_pipeline is not None and state.template_store is not None:
        try:
            server_pins, _ = derive_live_pins(
                db, pipeline=state.face_pipeline, store=state.template_store
            )
        except ValueError:
            server_pins = {"model_hash_pin": "", "gallery_revision_pin": "", "threshold_id_pin": ""}
    approval = None
    if not force_revert and requested.upper() in {"AUTO_VALIDATED", "AUTO"}:
        # Fail closed: require nonempty server pins (never skip via None)
        approval = verify_active_approval(
            db,
            secret_key=state.settings.secret_key,
            kind="AUTO_VALIDATED",
            camera_id=camera_id,
            model_hash_pin=server_pins["model_hash_pin"] or None,
            gallery_revision_pin=server_pins["gallery_revision_pin"] or None,
            threshold_id_pin=server_pins["threshold_id_pin"] or None,
            require_pins=True,
            require_camera_id=True,
        )
        if approval is not None and not approval.valid:
            approval = None
    allow_validated = approval is not None and approval.valid
    mode = effective_auto_mode(
        requested if requested.upper() != "AUTO_VALIDATED" else "AUTO",
        validated=allow_validated and not force_revert,
        reverted=force_revert,
    )
    if requested.upper() == "AUTO_VALIDATED" and not allow_validated:
        mode = effective_auto_mode("AUTO", validated=False)
    if force_revert:
        revoke_approvals(db, kind="AUTO_VALIDATED", camera_id=camera_id, reason="OPERATOR_ROLLBACK")
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
    # Persist server pins (not client-supplied unverified hashes)
    qs.model_hash_pin = server_pins["model_hash_pin"] or qs.model_hash_pin or ""
    qs.gallery_revision_pin = server_pins["gallery_revision_pin"] or qs.gallery_revision_pin or ""
    qs.threshold_id_pin = server_pins["threshold_id_pin"] or qs.threshold_id_pin or ""
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
        {
            "actor": user.username,
            "requested": requested,
            "effective": mode.value,
            "pins_source": "SERVER_DERIVED",
        },
        ensure_ascii=False,
    )
    db.flush()
    return _quality_settings_out(qs)


@router.post("/{camera_id}/quality/evaluation/run", dependencies=[Depends(require_csrf)])
def run_ab_evaluation(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Client-supplied pairs → UNTRUSTED_IMPORT only. Never promotable / never AUTO_VALIDATED."""
    import uuid

    from app.services.evidence_store import record_untrusted_ab_import
    from app.services.server_pins import derive_live_pins
    from app.vision.faces.paired_ab import EvaluationInputError, evaluate_pairs

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    pairs = body.get("pairs") or []
    if not isinstance(pairs, list):
        raise HTTPException(status_code=422, detail="pairs phải là danh sách")
    # Reject fabricated LIVE/REAL claims in request body — trust class ignores them
    claimed = str(body.get("source_mix") or body.get("claimed_source") or "")
    try:
        result = evaluate_pairs(pairs)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    pins = {"model_hash_pin": "", "gallery_revision_pin": "", "threshold_id_pin": ""}
    if state.face_pipeline is not None and state.template_store is not None:
        try:
            pins, _ = derive_live_pins(db, pipeline=state.face_pipeline, store=state.template_store)
        except ValueError:
            pass
    run_id = str(uuid.uuid4())
    mix = ",".join(sorted((result.get("by_source") or {}).keys())) or claimed or "EMPTY"
    metrics = {k: result[k] for k in ("original", "enhanced", "paired", "latency_ms") if k in result}
    blockers = list(result.get("blockers") or [])
    if any(x.upper() in {"LIVE", "REAL", "CAMERA_LIVE"} for x in mix.replace(";", ",").split(",")):
        blockers.append("CLIENT_CLAIMED_LIVE_IGNORED")
    ab = record_untrusted_ab_import(
        db,
        camera_id=camera_id,
        run_id=run_id,
        source_mix=mix,
        sample_count=int(result.get("samples") or 0),
        metrics=metrics,
        blockers=blockers,
        operator=user.username,
        pins=pins,
        clock=SystemClock().now_utc(),
    )
    return {
        "run_id": run_id,
        "camera_id": camera_id,
        "result": result,
        "evidence_class": ab.evidence_class,
        "can_auto_enable_enhancement": False,
        "approval_status": ab.approval_status,
        "operator": user.username,
        "note_vi": (
            "Import client = UNTRUSTED_IMPORT. Không đủ AUTO_VALIDATED dù gắn nhãn LIVE/REAL."
        ),
    }


@router.get("/{camera_id}/quality/report")
def redacted_quality_report(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    download: bool = False,
):
    """Export-safe report: camera_id/profile/status only — no URI, faces, embeddings."""
    from fastapi.responses import Response

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
    payload = {
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
        "settings_flag_camera_lab": bool(state.settings.camera_lab_pass),
        "settings_flag_face_pilot": bool(state.settings.face_pilot_pass),
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "secrets_present": False,
        "note_vi": (
            "Báo cáo đã ẩn URI/mật khẩu/ảnh khuôn mặt/embeddings. "
            "Cờ cấu hình ≠ phê duyệt PHYSICAL_VERIFIED đã ký."
        ),
    }
    if download:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="mypc-camera-{camera_id}-quality-report.json"'
            },
        )
    return payload


@router.post("/{camera_id}/evidence/record", dependencies=[Depends(require_csrf)])
def record_pilot_evidence(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """
    Record lab/face-pilot evidence. PHYSICAL_VERIFIED only when LIVE measured fields match
    registry health — admin checkbox alone is rejected.
    """
    from app.services.evidence_store import (
        EVIDENCE_LIVE_PENDING,
        EVIDENCE_PHYSICAL,
        EVIDENCE_UNTRUSTED_IMPORT,
        create_evidence,
    )
    from app.services.server_pins import derive_live_pins

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if body.get("admin_confirm") or body.get("checkbox_pass"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CHECKBOX_REJECTED",
                "message_vi": "Không chấp nhận checkbox admin làm bằng chứng vật lý.",
            },
        )
    kind = str(body.get("kind") or "")
    want_class = str(body.get("evidence_class") or EVIDENCE_LIVE_PENDING).upper()
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    try:
        pins, _ = derive_live_pins(db, pipeline=state.face_pipeline, store=state.template_store)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    reg = state.camera_registry
    bound = reg.get(camera_id) if reg else None
    h = bound.gateway.health() if bound else None
    provenance = bound.provenance.value if bound else ""
    measured_w = int(h.native_width) if h and h.native_width else 0
    measured_h = int(h.native_height) if h and h.native_height else 0
    fps = float(h.fps_estimate) if h and h.fps_estimate else None
    config_revision = bound.config_revision if bound else ""

    if want_class == EVIDENCE_PHYSICAL:
        if provenance != "CAMERA_LIVE" or measured_w <= 0 or measured_h <= 0:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PHYSICAL_REQUIRES_LIVE_DECODE",
                    "message_vi": (
                        "PHYSICAL_VERIFIED cần nguồn CAMERA_LIVE đã giải mã (DECODED_MEASURED). "
                        "Môi trường cloud/MOCK không đủ."
                    ),
                },
            )
        claim_w = int(body.get("observed_width") or 0)
        claim_h = int(body.get("observed_height") or 0)
        if claim_w != measured_w or claim_h != measured_h:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "OBSERVED_SIZE_MISMATCH",
                    "message_vi": "Kích thước khai báo không khớp khung LIVE đã đo trên server.",
                },
            )
        if kind == "FACE_PILOT":
            known = int(body.get("labeled_known") or 0)
            unknown = int(body.get("labeled_unknown") or 0)
            if known < 1 or unknown < 1:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "FACE_PILOT_LABELS_REQUIRED",
                        "message_vi": "FACE_PILOT cần số mẫu labeled known và unknown (>0).",
                    },
                )
        evidence_class = EVIDENCE_PHYSICAL
    elif want_class == EVIDENCE_UNTRUSTED_IMPORT:
        evidence_class = EVIDENCE_UNTRUSTED_IMPORT
    else:
        evidence_class = EVIDENCE_LIVE_PENDING

    try:
        ev = create_evidence(
            db,
            kind=kind,
            evidence_class=evidence_class,
            camera_id=camera_id,
            operator=user.username,
            pins=pins,
            config_revision=config_revision,
            provenance=provenance,
            decoded_w=measured_w or None,
            decoded_h=measured_h or None,
            fps_measured=fps,
            windows_host=str(body.get("windows_host") or "")[:128],
            labeled_known=int(body.get("labeled_known") or 0),
            labeled_unknown=int(body.get("labeled_unknown") or 0),
            note_vi=str(body.get("note_vi") or ""),
            ab_run_id=str(body.get("ab_run_id") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "evidence_id": ev.evidence_id,
        "kind": ev.kind,
        "evidence_class": ev.evidence_class,
        "camera_id": camera_id,
        "decoded_measured": {"width": measured_w or None, "height": measured_h or None, "fps": fps},
        "camera_lab_pass": False,
        "note_vi": "Đã ghi bằng chứng (không chứa ảnh/mật khẩu). PHYSICAL_VERIFIED vẫn cần máy Windows LAN.",
    }


@router.post("/{camera_id}/quality/approvals", dependencies=[Depends(require_csrf)])
def issue_pilot_approval(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Issue HMAC-signed approval only with PHYSICAL_VERIFIED evidence + server pins."""
    from app.models.entities import AbEvaluationRun
    from app.services.evidence_store import ab_run_promotable, require_physical_evidence
    from app.services.pilot_approval import issue_approval, verify_active_approval
    from app.services.server_pins import derive_live_pins

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if body.get("admin_confirm") or body.get("checkbox_pass"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CHECKBOX_REJECTED",
                "message_vi": "Không ký phê duyệt từ checkbox — cần evidence_id PHYSICAL_VERIFIED.",
            },
        )
    kind = str(body.get("kind") or "")
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline/gallery chưa sẵn sàng để suy pin.")
    try:
        pins, gallery = derive_live_pins(
            db, pipeline=state.face_pipeline, store=state.template_store
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    for key in ("model_hash_pin", "gallery_revision_pin", "threshold_id_pin"):
        client_val = str(body.get(key) or "").strip()
        if client_val and client_val != pins[key]:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CLIENT_PIN_MISMATCH",
                    "message_vi": f"Pin {key} client không khớp giá trị server-derived.",
                },
            )

    evidence_id = str(body.get("evidence_id") or "").strip()
    ab_run_id = str(body.get("ab_run_id") or "").strip()

    if kind in {"CAMERA_LAB", "FACE_PILOT"}:
        ev = require_physical_evidence(
            db, kind=kind, camera_id=camera_id, evidence_id=evidence_id, pins=pins
        )
        if not ev.valid:
            raise HTTPException(
                status_code=422,
                detail={"code": ev.code, "message_vi": ev.reason_vi},
            )

    if kind == "AUTO_VALIDATED":
        if not ab_run_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "AB_RUN_REQUIRED",
                    "message_vi": "AUTO_VALIDATED yêu cầu ab_run_id từ chạy A/B server.",
                },
            )
        ab = db.scalar(select(AbEvaluationRun).where(AbEvaluationRun.run_id == ab_run_id))
        if ab is None or ab.camera_id != camera_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "AB_RUN_INVALID",
                    "message_vi": "ab_run_id không tồn tại hoặc không gắn đúng camera.",
                },
            )
        ok, code = ab_run_promotable(ab)
        if not ok:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": code,
                    "message_vi": (
                        "AB chưa PHYSICAL_VERIFIED/APPROVED hoặc can_auto_enable=false "
                        "hoặc còn blocker nặng — từ chối AUTO_VALIDATED."
                    ),
                },
            )
        for need_kind in ("CAMERA_LAB", "FACE_PILOT"):
            prior = verify_active_approval(
                db,
                secret_key=state.settings.secret_key,
                kind=need_kind,
                camera_id=camera_id,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                require_pins=True,
                require_camera_id=True,
            )
            if prior is None or not prior.valid:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "PILOT_EVIDENCE_MISSING",
                        "message_vi": f"AUTO_VALIDATED cần {need_kind} đã ký (cùng pin/camera).",
                    },
                )
        if gallery.status != "OK":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "BLOCKED_GALLERY",
                    "message_vi": "Gallery ACTIVE trống/blocked — không cấp AUTO_VALIDATED.",
                },
            )
        evidence_id = evidence_id or ab_run_id

    try:
        rec = issue_approval(
            db,
            secret_key=state.settings.secret_key,
            kind=kind,
            camera_id=camera_id,
            issued_by=user.username,
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
            ab_run_id=ab_run_id,
            evidence_id=evidence_id,
            note_vi=str(body.get("note_vi") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "approval_id": rec.approval_id,
        "kind": rec.kind,
        "camera_id": camera_id,
        "evidence_id": evidence_id or None,
        "model_hash_pin": pins["model_hash_pin"],
        "gallery_revision_pin": pins["gallery_revision_pin"],
        "threshold_id_pin": pins["threshold_id_pin"],
        "ab_run_id": ab_run_id or None,
        "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
        "pins_source": "SERVER_DERIVED",
        "camera_lab_pass": False,
        "note_vi": "Đã ký phê duyệt server — HMAC không chứng minh quan sát vật lý ngoài evidence_id.",
    }


@router.post("/{camera_id}/live/observe-shadow", dependencies=[Depends(require_csrf)])
def live_observe_shadow(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """
    Verified LIVE frame → detect/match → shadow observation metadata.
    Never writes authoritative attendance until CAMERA_LAB + FACE_PILOT signed.
    """
    from app.vision.camera.registry import FrameAccessError
    from app.vision.faces.types import MatchOutcome

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    reg = state.camera_registry
    if reg is None:
        raise HTTPException(status_code=503, detail="Registry chưa sẵn sàng")
    try:
        bound, fr = reg.get_frame(
            camera_id,
            require_live=True,
            for_biometric=True,
            allow_stale=False,
            max_age_s=3.0,
        )
    except FrameAccessError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message_vi": exc.message_vi}) from exc

    from app.services.pilot_approval import verify_active_approval
    from app.services.server_pins import derive_live_pins

    # Signed approvals are the trust source — settings flags alone never open the gate
    lab_ok = False
    pilot_ok = False
    gallery_status = "BLOCKED_GALLERY"
    gallery_count = 0
    gallery_pairs: list = []
    if state.face_pipeline is not None and state.template_store is not None:
        try:
            pins, snap = derive_live_pins(
                db, pipeline=state.face_pipeline, store=state.template_store
            )
            gallery_status = snap.status
            gallery_count = snap.count
            gallery_pairs = list(snap.pairs)
            lab = verify_active_approval(
                db,
                secret_key=state.settings.secret_key,
                kind="CAMERA_LAB",
                camera_id=camera_id,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                require_pins=True,
                require_camera_id=True,
            )
            face = verify_active_approval(
                db,
                secret_key=state.settings.secret_key,
                kind="FACE_PILOT",
                camera_id=camera_id,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                require_pins=True,
                require_camera_id=True,
            )
            lab_ok = bool(lab and lab.valid)
            pilot_ok = bool(face and face.valid)
        except ValueError:
            gallery_pairs = []
    gated = not (lab_ok and pilot_ok)
    pixels = fr.clone_pixels()
    # Never expose raw employee match to unauthorized shadow when gallery blocked
    if gallery_status != "OK":
        match_outcome = "BLOCKED_GALLERY"
        employee_id = None
        similarity = None
    else:
        result = state.face_pipeline.verify(pixels, gallery=gallery_pairs)
        match_outcome = result.outcome.value
        # Pseudonymous for shadow: only return employee_id when not gated
        employee_id = result.employee_id if not gated else None
        similarity = result.similarity
    return {
        "shadow": True,
        "authoritative": False,
        "gated": gated,
        "camera_id": camera_id,
        "frame_id": fr.frame_id,
        "config_revision": bound.config_revision,
        "provenance": fr.provenance.value,
        "clock_trust": fr.clock_trust.value,
        "receive_time_utc": fr.receive_time_utc.isoformat(),
        "pixel_sha256": fr.pixel_sha256,
        "match_outcome": match_outcome,
        "employee_id": employee_id,
        "similarity": similarity,
        "gallery_status": gallery_status,
        "gallery_count": gallery_count,
        "operator": user.username,
        "note_vi": (
            "Quan sát bóng từ khung LIVE đã xác minh nguồn. "
            "Chưa ghi công chính thức — cần CAMERA_LAB + FACE_PILOT đã ký (không tin cờ cấu hình)."
            if gated
            else "Đã có phê duyệt đã ký — vẫn chỉ shadow; không ghi AM/PM chính thức tại endpoint này."
        ),
        "camera_lab_pass": lab_ok,
        "face_pilot_pass": pilot_ok,
        "settings_flag_camera_lab": bool(state.settings.camera_lab_pass),
        "would_reject_unknown": match_outcome
        in {
            MatchOutcome.UNKNOWN.value,
            MatchOutcome.AMBIGUOUS.value,
            MatchOutcome.NO_FACE.value,
            "BLOCKED_GALLERY",
        },
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

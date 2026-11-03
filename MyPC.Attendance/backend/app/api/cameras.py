"""Camera setup, diagnostics, preview, ROI — CAMERA_MANAGE + SSRF/ROI guards."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.api.db_finalize_route import FinalizingAPIRoute
import math
import time

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
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
from app.models.entities import AuditLog, CameraDevice, RecognitionRegion, User
from app.services.camera_credential_service import (
    apply_camera_credentials,
    safe_rtsp_uri_for_edit,
)
from app.core.utc_time import utc_now

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"], route_class=FinalizingAPIRoute)


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
    credential_action: str = "keep"  # keep|replace|remove


class CameraUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    model: str | None = None
    firmware: str | None = None
    rtsp_url_override: str | None = None
    mock_mode: bool | None = None
    enabled: bool | None = None
    username: str = ""
    password: str = ""
    credential_action: str = "keep"


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
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    include_archived: bool = False,
    filter: str = "ALL",  # ALL|ACTIVE|ARCHIVED|MOCK|LIVE
    q: str = "",
) -> list[dict]:
    flt = (filter or "ALL").strip().upper()
    stmt = select(CameraDevice)
    if flt == "ARCHIVED":
        stmt = stmt.where(CameraDevice.archived.is_(True))
    elif not include_archived:
        stmt = stmt.where(CameraDevice.archived.is_(False))
    rows = list(db.scalars(stmt.order_by(CameraDevice.id)).all())
    out = [_cam_out(r, state) for r in rows]
    if flt == "MOCK":
        out = [c for c in out if c.get("mock_mode")]
    elif flt == "LIVE":
        out = [c for c in out if c.get("live_verified") or (c.get("runtime") or {}).get("live_decoded")]
    elif flt == "ACTIVE":
        out = [c for c in out if not c.get("archived") and c.get("enabled")]
    needle = (q or "").strip().lower()
    if needle:
        out = [
            c
            for c in out
            if needle in str(c.get("name") or "").lower()
            or needle in str(c.get("host") or "").lower()
            or needle == str(c.get("id"))
        ]
    return out


@router.get("/duplicates/dry-run")
def duplicates_dry_run(
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Preview duplicate host/path groups — never deletes. Owner must pick explicitly."""
    rows = db.scalars(
        select(CameraDevice).where(CameraDevice.archived.is_(False)).order_by(CameraDevice.id)
    ).all()
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = f"{(r.host or '').strip().lower()}|{safe_rtsp_uri_for_edit(r.rtsp_url_override or '')}"
        if not (r.host or r.rtsp_url_override):
            continue
        groups.setdefault(key, []).append(
            {
                "id": r.id,
                "name": r.name,
                "mock_mode": r.mock_mode,
                "live_verified": bool((_cam_out(r, state).get("live_verified"))),
                "connection_status": getattr(r, "connection_status", None),
            }
        )
    dupes = [
        {"key": k, "cameras": v, "count": len(v)}
        for k, v in groups.items()
        if len(v) > 1
    ]
    return {
        "dry_run": True,
        "duplicate_groups": dupes,
        "message_vi": (
            "Chỉ xem trước — không xóa tự động. "
            "Giữ camera LIVE đang dùng (# thấp nhất / đã giải mã); archive hoặc xóa cứng bản sao không còn lịch sử."
        ),
        "auto_delete": False,
    }


@router.post("", dependencies=[Depends(require_csrf)])
def create_camera(
    body: CameraIn,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    try:
        host = validate_camera_host(body.host, allow_empty=True)
        rtsp = validate_rtsp_url(body.rtsp_url_override, allow_empty=True)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Soft duplicate guard — same host + same safe path among active cameras
    if host and rtsp:
        safe_new = safe_rtsp_uri_for_edit(rtsp)
        existing = db.scalars(
            select(CameraDevice).where(
                CameraDevice.archived.is_(False),
                CameraDevice.host == host,
            )
        ).all()
        for ex in existing:
            if safe_rtsp_uri_for_edit(ex.rtsp_url_override) == safe_new and safe_new:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CAMERA_DUPLICATE",
                        "message_vi": (
                            f"Đã có camera #{ex.id} cùng host/đường dẫn. "
                            "Hãy chọn và sửa camera hiện có thay vì tạo thêm."
                        ),
                        "existing_id": ex.id,
                    },
                )

    now = SystemClock().now_utc()
    import uuid as _uuid

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
        connection_status="CONFIG_SAVED" if (host or rtsp) else "UNKNOWN",
        username_hint=(body.username or "").strip(),
        lifecycle_id=_uuid.uuid4().hex,
    )
    db.add(row)
    db.flush()
    action = (body.credential_action or "keep").strip().lower()
    if body.password or action == "replace":
        action = "replace"
    try:
        cred = apply_camera_credentials(
            state.secrets,
            camera_id=row.id,
            current_secret_ref="",
            current_username_hint="",
            action=action if action in {"keep", "replace", "remove"} else "keep",
            username=body.username,
            password=body.password,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row.secret_ref = cred.secret_ref
    row.username_hint = cred.username_hint
    db.add(
        RecognitionRegion(
            camera_id=row.id,
            name="arrival",
            norm_rect_json=json.dumps({"x": 0.3, "y": 0.05, "w": 0.4, "h": 0.25}),
        )
    )
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_CREATE",
            entity_type="camera",
            entity_id=str(row.id),
            reason="secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    db.flush()
    return _cam_out(row, state)


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
    if row.archived:
        raise HTTPException(status_code=409, detail="Camera đã lưu trữ — không gắn LIVE.")
    username = (body.get("username") or "").strip()
    # Distinguish missing password from empty overwrite (PR11-HF)
    password_provided = "password" in body and body.get("password") is not None
    password = body.get("password") if password_provided else None
    credential_action = str(body.get("credential_action") or "keep").strip().lower()
    if password_provided and password not in (None, "") and credential_action == "keep":
        credential_action = "replace"
    try:
        cred = apply_camera_credentials(
            state.secrets,
            camera_id=camera_db_id,
            current_secret_ref=row.secret_ref or "",
            current_username_hint=row.username_hint or "",
            action=credential_action if credential_action in {"keep", "replace", "remove"} else "keep",  # type: ignore[arg-type]
            username=username,
            password="" if password is None else str(password),
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row.secret_ref = cred.secret_ref
    row.username_hint = cred.username_hint
    # Persist editable RTSP path (no userinfo) on configure
    row.rtsp_url_override = safe_uri
    # Same-request: prefer staged blob until post-commit promote
    read_ref = cred.staged_ref or row.secret_ref
    stored = state.secrets.get_camera_secret(read_ref) if read_ref else None
    if stored and stored.get("username"):
        from urllib.parse import quote

        safe_uri = (
            f"{endpoint.scheme}://{quote(stored['username'], safe='')}:{quote(stored.get('password') or '', safe='')}"
            f"@{pinned_host}:{endpoint.port}{endpoint.path}"
        )
    elif credential_action == "replace" and username and password:
        from urllib.parse import quote

        safe_uri = (
            f"{endpoint.scheme}://{quote(username, safe='')}:{quote(str(password), safe='')}"
            f"@{pinned_host}:{endpoint.port}{endpoint.path}"
        )
    elif not stored:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CREDENTIAL_REQUIRED",
                "message_vi": (
                    "Chưa có mật khẩu camera đã lưu. "
                    "Nhập mật khẩu mới (đổi mật khẩu tường minh) hoặc lưu credential trước."
                ),
            },
        )
    if state.camera_registry is None:
        from app.vision.camera.registry import CameraSourceRegistry

        state.camera_registry = CameraSourceRegistry()
    from app.vision.camera.gateway import physical_stream_fingerprint

    fp = physical_stream_fingerprint(safe_uri)
    # Refuse starting a second decode for same physical stream already leased by another camera
    holders = state.camera_registry.lease_holders(fp)
    if holders and camera_db_id not in holders:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PHYSICAL_STREAM_IN_USE",
                "message_vi": (
                    f"Luồng vật lý đang được camera #{holders[0]} giải mã. "
                    "Dừng LIVE camera đó trước, hoặc dùng chung profile hiện có — "
                    "không mở decoder RTSP trùng."
                ),
                "holders": holders,
                "stream_fingerprint": fp,
            },
        )
    gw = LiveRTSPGateway(safe_uri, camera_id=str(camera_db_id), transport="tcp")
    # Bind first so config_revision is synced before any frames are published
    bound = state.camera_registry.bind(
        camera_db_id,
        gw,
        provenance=StreamProvenance.CAMERA_LIVE,
        profile=profile,
        stream_fingerprint=fp,
    )
    # Start the (possibly shared) gateway after bind
    bound.gateway.start()
    state.camera_gateway = bound.gateway  # legacy pointer
    # If SQL rolls back, do not leave LIVE runtime bound to uncommitted config (audit #4)
    from app.services.secret_fs_outbox import register_runtime_compensate

    def _undo_live_bind() -> None:
        if state.camera_registry is not None:
            state.camera_registry.unbind(camera_db_id)
        if state.camera_gateway is bound.gateway:
            state.camera_gateway = None

    register_runtime_compensate(db, _undo_live_bind)
    row.mock_mode = False
    from app.models.entities import CameraLiveBinding
    from app.services.pilot_approval import revoke_approvals

    binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_db_id))
    now = SystemClock().now_utc()
    if binding is None:
        binding = CameraLiveBinding(camera_id=camera_db_id)
        db.add(binding)
    else:
        # Profile/config change invalidates prior signed approvals + lab runs
        if binding.config_revision and binding.config_revision != bound.config_revision:
            revoke_approvals(
                db, camera_id=camera_db_id, reason="CAMERA_CONFIG_REVISION_CHANGED"
            )
            from app.services.lab_run_service import revoke_lab_runs_for_camera

            revoke_lab_runs_for_camera(
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
    row.mock_mode = False
    row.enabled = True
    row.config_revision = bound.config_revision
    row.connection_status = "CONFIG_SAVED"  # waiting for decoded frame — NOT LIVE verified
    row.last_health_status = "CONFIG_SAVED"
    row.last_health_at = now
    return {
        "ok": True,
        "camera_id": camera_db_id,
        "config_revision": bound.config_revision,
        "connection_status": "CONFIG_SAVED",
        "live_verified": False,
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
            "Đã lưu cấu hình LIVE — đang chờ khung hình giải mã (CONFIG_SAVED). "
            "Chưa phải LIVE verified. CAMERA_LAB_PASS vẫn BLOCKED."
        ),
        "operator": user.username,
    }


@router.post("/{camera_id}/gateway/stop", dependencies=[Depends(require_csrf)])
def stop_live_gateway(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if state.camera_registry is not None:
        state.camera_registry.unbind(camera_id)
    row.enabled = False
    row.connection_status = "STOPPED"
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_STOP_LIVE",
            entity_type="camera",
            entity_id=str(camera_id),
            reason="secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    db.flush()
    return {
        "ok": True,
        "camera_id": camera_id,
        "connection_status": "STOPPED",
        "message_vi": "Đã dừng gateway LIVE cho camera này.",
    }


@router.post("/{camera_id}/rtsp/test", dependencies=[Depends(require_csrf)])
def test_rtsp(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Operator-triggered staged RTSP probe — single auth attempt, no brute force."""
    from app.vision.camera.rtsp_probe import parse_rtsp_parts, probe_rtsp_stages

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if row.archived:
        raise HTTPException(status_code=409, detail="Camera đã lưu trữ")
    uri = (body.get("rtsp_uri") or row.rtsp_url_override or "").strip()
    if not uri and row.host:
        path = str(body.get("path") or "/ch1/main")
        uri = f"rtsp://{row.host}:554{path}"
    if not uri:
        raise HTTPException(status_code=422, detail="Thiếu URI/host để kiểm RTSP")
    try:
        endpoint_uri = validate_rtsp_url(uri, allow_empty=False)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    host, port, path = parse_rtsp_parts(endpoint_uri)
    stored = state.secrets.get_camera_secret(row.secret_ref) if row.secret_ref else None
    username = (body.get("username") or "").strip() or (stored or {}).get("username") or row.username_hint
    # Password only from body when replace; else reuse stored (never echo)
    password = body.get("password")
    if password in (None, ""):
        password = (stored or {}).get("password")
    try_auth = bool(username and password)
    result = probe_rtsp_stages(
        camera_id=camera_id,
        config_revision=row.config_revision or "",
        host=host or row.host,
        port=port,
        path=path,
        username=username if try_auth else None,
        password=password if try_auth else None,
        try_auth=try_auth,
    )
    # Handshake lane ≠ LIVE decoder.
    # Probe outcomes always stay in last_health_status + response handshake fields.
    # Never overwrite DB connection_status while an independently healthy LIVE decoder
    # is operational for this camera (AUTH/404/UNKNOWN/CONFIG_SAVED alike).
    # When LIVE is down, definitive AUTH/404/DISABLED may persist for operator visibility.
    handshake = result.overall_status
    prior_status = row.connection_status
    row.last_health_at = SystemClock().now_utc()
    row.last_health_status = f"HANDSHAKE:{handshake}"
    live_ok = False
    try:
        gh = state.camera_registry.health().get("sources") if state.camera_registry else None
        if gh:
            for s in gh:
                if (
                    str(s.get("camera_id")) == str(camera_id)
                    and s.get("operationally_ready")
                    and str(s.get("decoder_status") or "") == "OK"
                ):
                    live_ok = True
                    break
    except Exception:  # noqa: BLE001
        live_ok = False
    definitive = {
        "AUTH_FAILED",
        "STREAM_NOT_FOUND",
        "RTSP_DISABLED_OR_UNAVAILABLE",
    }
    clobber = False
    preserve_reason = ""
    if live_ok:
        preserve_reason = "LIVE_DECODER_HEALTHY"
        # leave connection_status unchanged
    elif handshake in definitive:
        row.connection_status = handshake
        clobber = True
    # else CONFIG_SAVED / UNKNOWN / etc. without LIVE: leave unchanged
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_RTSP_TEST",
            entity_type="camera",
            entity_id=str(camera_id),
            reason=(
                f"handshake={handshake}; handshake_only=true; "
                f"clobber={clobber}; live_ok={live_ok}; "
                f"preserve={preserve_reason or 'n/a'}; secrets_redacted=true"
            ),
            timestamp=utc_now(),
        )
    )
    db.flush()
    payload = result.as_dict()
    payload["handshake_only"] = True
    payload["rtsp_handshake_status"] = handshake
    payload["handshake_inconclusive"] = handshake == "UNKNOWN"
    payload["connection_status_prior"] = prior_status
    payload["connection_status_persisted"] = row.connection_status
    payload["connection_status_clobbered"] = clobber
    payload["live_status_preserved"] = bool(live_ok and not clobber)
    payload["live_decoder_operational"] = live_ok
    payload["measured_at_utc"] = SystemClock().now_utc().isoformat().replace("+00:00", "Z")
    payload["note_vi"] = (
        "Kết quả này là RTSP HANDSHAKE ONLY — không thay thế LIVE_DECODED. "
        "ONVIF/FIRST_FRAME trong probe không chứng minh decoder đang chạy. "
        "UNKNOWN/AUTH/404 không ghi đè connection_status khi LIVE decoder đang healthy."
    )
    return payload



@router.get("/{camera_id}")
def get_camera(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    return _cam_out(row, state, detail=True)


@router.patch("/{camera_id}", dependencies=[Depends(require_csrf)])
def update_camera(
    camera_id: int,
    body: CameraUpdate,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if row.archived:
        raise HTTPException(
            status_code=409,
            detail="Camera đã lưu trữ — hãy khôi phục trước khi sửa.",
        )
    try:
        if body.host is not None:
            row.host = validate_camera_host(body.host, allow_empty=True)
        if body.rtsp_url_override is not None:
            row.rtsp_url_override = validate_rtsp_url(body.rtsp_url_override, allow_empty=True)
    except ValidationErrorVi as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.name is not None:
        row.name = body.name
    if body.model is not None:
        row.model = body.model
    if body.firmware is not None:
        row.firmware = body.firmware
    if body.mock_mode is not None:
        row.mock_mode = body.mock_mode
    if body.enabled is not None:
        row.enabled = body.enabled
        if not body.enabled and state.camera_registry is not None:
            state.camera_registry.unbind(camera_id)
            row.connection_status = "STOPPED"

    action = (body.credential_action or "keep").strip().lower()
    if action not in {"keep", "replace", "remove"}:
        action = "keep"
    try:
        cred = apply_camera_credentials(
            state.secrets,
            camera_id=row.id,
            current_secret_ref=row.secret_ref or "",
            current_username_hint=row.username_hint or "",
            action=action,  # type: ignore[arg-type]
            username=body.username,
            password=body.password,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row.secret_ref = cred.secret_ref
    row.username_hint = cred.username_hint
    row.connection_status = row.connection_status or "CONFIG_SAVED"
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_UPDATE",
            entity_type="camera",
            entity_id=str(row.id),
            reason=f"credential_action={cred.action}; secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    db.flush()
    return _cam_out(row, state, detail=True)


@router.post("/{camera_id}/archive", dependencies=[Depends(require_csrf)])
def archive_camera(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if state.camera_registry is not None:
        state.camera_registry.unbind(camera_id)
    row.archived = True
    row.archived_at = utc_now()
    row.enabled = False
    row.connection_status = "STOPPED"
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_ARCHIVE",
            entity_type="camera",
            entity_id=str(row.id),
            reason="soft_delete; history_preserved; secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    db.flush()
    return {
        "ok": True,
        "id": row.id,
        "archived": True,
        "message_vi": "Đã lưu trữ camera — lịch sử chấm công/quan sát được giữ nguyên.",
    }


@router.post("/{camera_id}/restore", dependencies=[Depends(require_csrf)])
def restore_camera(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    row.archived = False
    row.archived_at = None
    row.connection_status = "CONFIG_SAVED"
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_RESTORE",
            entity_type="camera",
            entity_id=str(row.id),
            reason="secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    db.flush()
    return {"ok": True, "id": row.id, "archived": False, "camera": _cam_out(row, state, detail=True)}


@router.delete("/{camera_id}", dependencies=[Depends(require_csrf)])
def delete_camera(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
    force: bool = False,
) -> dict:
    """Permanent delete ONLY when no historical dependents. Prefer archive."""
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    blockers = _camera_delete_blockers(db, camera_id)
    if blockers["total"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CAMERA_HAS_HISTORY",
                "message_vi": (
                    "Camera còn dữ liệu lịch sử — không xóa cứng. "
                    "Hãy dùng Lưu trữ (archive) để ẩn khỏi danh sách."
                ),
                "blockers": blockers,
            },
        )
    if blockers["total"] > 0 and force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CAMERA_FORCE_DELETE_DENIED",
                "message_vi": "Từ chối xóa cứng khi còn phụ thuộc lịch sử (bảo vệ dữ liệu).",
                "blockers": blockers,
            },
        )
    if state.camera_registry is not None:
        state.camera_registry.unbind(camera_id)
    secret_ref = row.secret_ref or ""
    # Capture immutable instance id before row delete (C14 — SQLite may reuse PK)
    camera_lifecycle_id = (getattr(row, "lifecycle_id", None) or "").strip()
    # Cascade-clean config-only dependents (not historical attendance / evidence)
    from app.models.entities import (
        CameraLiveBinding,
        CameraQualitySettings,
        CameraStreamProfile,
        RecognitionRegion,
    )

    from sqlalchemy.exc import IntegrityError

    try:
        for model in (RecognitionRegion, CameraQualitySettings, CameraStreamProfile, CameraLiveBinding):
            for dep in list(db.scalars(select(model).where(model.camera_id == camera_id)).all()):  # type: ignore[attr-defined]
                db.delete(dep)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CAMERA_CONFIG_CLEANUP_FK",
                "message_vi": "Không dọn được cấu hình phụ thuộc — dùng Lưu trữ.",
                "blockers": _camera_delete_blockers(db, camera_id),
            },
        ) from exc
    # Re-check blockers after config cleanup (should still be zero for hard-delete path)
    blockers_after = _camera_delete_blockers(db, camera_id)
    if blockers_after["total"] > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CAMERA_HAS_HISTORY",
                "message_vi": "Vẫn còn phụ thuộc lịch sử sau khi dọn cấu hình — dùng Lưu trữ.",
                "blockers": blockers_after,
            },
        )
    try:
        db.delete(row)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        blockers_now = _camera_delete_blockers(db, camera_id)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CAMERA_DELETE_FK_BLOCKED",
                "message_vi": (
                    "Không xóa cứng được do ràng buộc dữ liệu — dùng Lưu trữ. "
                    f"Chi tiết: {type(exc).__name__}"
                ),
                "blockers": blockers_now,
            },
        ) from exc
    except Exception:
        # Real operational / DB failures — do not mask as 409
        db.rollback()
        raise
    db.add(
        AuditLog(
            actor=user.username,
            action="CAMERA_DELETE",
            entity_type="camera",
            entity_id=str(camera_id),
            reason="hard_delete_unreferenced; secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    # Queue filesystem credential scrub on THIS session outbox only (P0-01).
    # Never delete camera-*.bin before durable DB commit; never share across requests.
    # hard_delete + lifecycle fence: old intents must not scrub a recreated camera id (C14).
    if secret_ref:
        from app.services.secret_fs_outbox import queue_delete

        queue_delete(
            db,
            secret_ref,
            camera_id=camera_id,
            camera_lifecycle_id=camera_lifecycle_id,
            hard_delete=True,
        )
    return {"ok": True, "deleted_id": camera_id, "credential_delete_deferred": bool(secret_ref)}


@router.get("/{camera_id}/delete-blockers")
def get_delete_blockers(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(CAMERA_MANAGE))],
) -> dict:
    """Preflight hard-delete — never mutates. Prefer archive when total > 0."""
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    blockers = _camera_delete_blockers(db, camera_id)
    return {
        "camera_id": camera_id,
        "can_hard_delete": blockers["total"] == 0,
        "prefer_archive": blockers["total"] > 0,
        "blockers": blockers,
        "message_vi": (
            "Có thể xóa cứng (không còn lịch sử)."
            if blockers["total"] == 0
            else "Còn phụ thuộc lịch sử — hãy Lưu trữ; không cascade xóa evidence/chấm công."
        ),
    }



def _encode_preview_jpeg(fr, *, max_w: int = 960, quality: int = 80) -> tuple[bytes, int, int]:
    import cv2

    pixels = fr.clone_pixels()
    h, w = pixels.shape[:2]
    if w > max_w:
        scale = max_w / float(w)
        pixels = cv2.resize(pixels, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", pixels, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG_ENCODE_FAILED")
    return buf.tobytes(), int(pixels.shape[1]), int(pixels.shape[0])


def _preview_from_frame(fr, *, live: bool, source: str, indicator_vi: str, view_mode: str = "SNAPSHOT") -> dict:
    import base64

    try:
        jpeg, pw, ph = _encode_preview_jpeg(fr)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PREVIEW_ENCODE_FAILED",
                "message_vi": "Không mã hóa được khung xem trước (không phải lỗi nội bộ ẩn).",
            },
        ) from exc
    return {
        "data_base64": base64.b64encode(jpeg).decode("ascii"),
        "mime": "image/jpeg",
        "indicator_vi": indicator_vi,
        "width": fr.width,
        "height": fr.height,
        "preview_width": pw,
        "preview_height": ph,
        "live": live,
        "view_mode": view_mode,
        "source": source,
        "provenance": fr.provenance.value,
        "decoder_status": fr.decoder_status.value,
        "frame_id": fr.frame_id,
        "config_revision": fr.config_revision,
        "clock_trust": fr.clock_trust.value,
        "pixel_sha256": fr.pixel_sha256,
        "receive_time_utc": fr.receive_time_utc.isoformat() if fr.receive_time_utc else None,
        "integrity_ok": bool(getattr(fr, "integrity_ok", True)),
        "size_source": "DECODED_MEASURED",
        "camera_lab_pass": False,
        "mock": source in {"DEMO", "MOCK"},
    }


def _resolve_preview_frame(camera_id: int, db: Session, state: AppState):
    """Shared preview/MJPEG source resolution — never silent MOCK for LIVE cameras."""
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if row.archived:
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMERA_ARCHIVED", "message_vi": "Camera đã lưu trữ — không xem trước."},
        )

    reg = state.camera_registry
    bound = reg.get(camera_id) if reg is not None else None

    if row.mock_mode and bound is None:
        if state.settings.is_production():
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MOCK_DISABLED_IN_PRODUCTION",
                    "message_vi": (
                        "Camera MOCK không dùng được cho xem LIVE trên máy production. "
                        "Hãy cấu hình RTSP thật hoặc bật demo_mode có chủ đích."
                    ),
                    "camera_lab_pass": False,
                },
            )
        from app.vision.camera.gateway import MockFrameGateway, StreamProvenance
        from app.vision.camera.registry import CameraSourceRegistry

        if reg is None:
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
            allow_stale=True,
            max_age_s=30.0,
            for_biometric=False,
            require_integrity=False,
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
    return row, bound, fr


@router.get("/{camera_id}/preview")
def preview(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """Still SNAPSHOT preview (not smooth LIVE). Prefer /preview/mjpeg for motion view."""
    try:
        _row, bound, fr = _resolve_preview_frame(camera_id, db, state)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PREVIEW_FAILED",
                "message_vi": f"Không lấy được khung xem trước: {type(exc).__name__}",
            },
        ) from exc
    live = bound.provenance.value == "CAMERA_LIVE"
    source = "REAL_CAMERA" if live else bound.provenance.value
    status = fr.decoder_status.value
    indicator = "SNAPSHOT — CAMERA THẬT" if live else (
        "SNAPSHOT — MOCK" if bound.provenance.value == "MOCK" else "SNAPSHOT — RECORDED"
    )
    if status == "STALE":
        indicator = f"{indicator} — STALE"
    elif status == "DEGRADED":
        indicator = f"{indicator} — DEGRADED (không dùng nhận diện)"
    out = _preview_from_frame(
        fr,
        live=live and status == "OK" and bool(getattr(fr, "integrity_ok", True)),
        source=source,
        indicator_vi=indicator,
        view_mode="SNAPSHOT",
    )
    out["stale"] = status == "STALE"
    out["degraded"] = status == "DEGRADED"
    out["operationally_ready"] = live and status == "OK" and bool(getattr(fr, "integrity_ok", True))
    out["ui_state"] = status if status in {"OK", "STALE", "DEGRADED"} else status
    return out


@router.get("/{camera_id}/preview/mjpeg")
def preview_mjpeg(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    max_fps: float = 12.0,
) -> StreamingResponse:
    """
    Authenticated multipart MJPEG LIVE view for localhost.
    Reuses the single server-side decoder; drops intermediate frames under load.
    Recognition still uses full-resolution immutable frames from the same gateway.
    """
    # Resolve once up-front so auth/404 fail before streaming headers
    _resolve_preview_frame(camera_id, db, state)
    fps = max(1.0, min(float(max_fps or 12.0), 20.0))
    interval = 1.0 / fps
    boundary = b"frame"

    def generate():
        last_id = ""
        while True:
            try:
                with state.session_factory() as sdb:
                    _row, bound, fr = _resolve_preview_frame(camera_id, sdb, state)
                if fr.frame_id == last_id:
                    time.sleep(interval)
                    continue
                last_id = fr.frame_id
                jpeg, _pw, _ph = _encode_preview_jpeg(fr, max_w=1280, quality=72)
                header = (
                    b"--" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n"
                    b"X-Decoder-Status: " + fr.decoder_status.value.encode("ascii") + b"\r\n"
                    b"X-View-Mode: LIVE_MJPEG\r\n"
                    b"\r\n"
                )
                yield header + jpeg + b"\r\n"
            except HTTPException:
                break
            except Exception:
                time.sleep(interval)
                continue
            time.sleep(interval)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary.decode('ascii')}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-View-Mode": "LIVE_MJPEG",
            "X-Camera-Lab-Pass": "false",
        },
    )


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
        # Settings staging flags ≠ signed CAMERA_LAB / FACE_PILOT pass
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "settings_flag_camera_lab": bool(state.settings.camera_lab_pass),
        "settings_flag_face_pilot": bool(state.settings.face_pilot_pass),
        "config_revision": bound.config_revision if bound else None,
        "provenance": bound.provenance.value if bound else None,
        "decoder_status": (
            h.decoder_status.value if h and hasattr(h.decoder_status, "value") else None
        ),
        "corrupt_frames": (h.extras or {}).get("corrupt_frames") if h else None,
        "hevc_ref_events": (h.extras or {}).get("hevc_ref_events") if h else None,
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


def _lab_run_http(exc: Exception) -> HTTPException:
    from app.services.lab_run_service import LabRunError

    if isinstance(exc, LabRunError):
        return HTTPException(
            status_code=422, detail={"code": exc.code, "message_vi": exc.message_vi}
        )
    return HTTPException(status_code=422, detail=str(exc))


def _lab_next_step(run: Any, layers: dict[str, Any]) -> dict[str, Any]:
    """Single next permitted action + unmet checklist — UI must not invent order."""
    from app.services.lab_run_service import (
        STATE_CREATED,
        STATE_LIVE_MEASURED,
        STATE_OWNER_REVIEWED,
        STATE_PHYSICAL,
        STATE_REJECTED,
    )

    state = run.state
    kind = run.kind
    checklist = {
        "lab_run_created": state != STATE_REJECTED and bool(run.run_id),
        "LIVE_SOURCE_MEASURED": bool(layers.get("LIVE_SOURCE_MEASURED")) or state in {
            STATE_LIVE_MEASURED, STATE_OWNER_REVIEWED, STATE_PHYSICAL
        },
        "owner_challenge_ready": state == STATE_LIVE_MEASURED,
        "PHYSICAL_CONNECTIVITY_REVIEWED": bool(layers.get("PHYSICAL_CONNECTIVITY_REVIEWED"))
        or state in {STATE_OWNER_REVIEWED, STATE_PHYSICAL},
        "evidence_physical_record": state == STATE_PHYSICAL,
        "signed_camera_lab_pass": False,  # always separate HMAC approval
        "face_pilot": (
            "N_A"
            if kind == "CAMERA_LAB"
            else ("APPROVED" if layers.get("FACE_PILOT_VALIDATION_APPROVED") else "PENDING")
        ),
    }
    if state == STATE_CREATED:
        next_action = "MEASURE_LIVE"
        next_vi = "Bước tiếp: Đo LIVE (khung phân biệt)."
        allowed = ["measure"]
    elif state == STATE_LIVE_MEASURED:
        next_action = "REVEAL_CHALLENGE_THEN_OWNER_REVIEW"
        next_vi = "Bước tiếp: Lấy challenge → Owner review (một toán tử)."
        allowed = ["reveal_challenge", "owner_review"]
    elif state == STATE_OWNER_REVIEWED:
        next_action = "PROMOTE_PHYSICAL"
        next_vi = (
            "Bước tiếp: Promote PHYSICAL evidence. "
            "Lớp PHYSICAL_VERIFIED ≠ CAMERA_LAB_PASS đã ký."
        )
        allowed = ["promote_physical"]
    elif state == STATE_PHYSICAL:
        next_action = "DONE_AWAITING_SIGNED_APPROVAL"
        next_vi = (
            "Đã có evidence PHYSICAL_VERIFIED. "
            "camera_lab_pass vẫn false cho đến khi có phê duyệt HMAC riêng. "
            "FACE_PILOT = N/A nếu kind=CAMERA_LAB."
        )
        allowed = ["export_json"]
    else:
        next_action = "START_NEW_RUN"
        next_vi = "Lab run từ chối/hết hạn — tạo run mới (không ghi đè evidence cũ)."
        allowed = ["start_new_run"]
    return {
        "next_action": next_action,
        "next_action_vi": next_vi,
        "allowed_actions": allowed,
        "checklist": checklist,
        "distinctions_vi": {
            "evidence_class_PHYSICAL_VERIFIED": "Bản ghi bằng chứng vật lý đã tạo sau promote.",
            "LIVE_SOURCE_MEASURED": "Đã đo khung LIVE phân biệt + FPS>0.",
            "camera_lab_pass": "Chỉ true sau phê duyệt HMAC đã ký — không phải UI text.",
            "face_pilot_pass": "Tách biệt; CAMERA_LAB không tự duyệt nhận diện.",
        },
    }


def _lab_run_out(run: Any) -> dict[str, Any]:
    """Sanitized lab-run view — never include owner_challenge (SEC02)."""
    import json as _json

    meta: dict[str, Any] = {}
    try:
        meta = _json.loads(run.metrics_json or "{}")
    except Exception:  # noqa: BLE001
        meta = {}
    layers = meta.get("evidence_layers") or {}
    face_status = meta.get("face_validation_status")
    if run.kind == "CAMERA_LAB":
        # Never show red "failed"/PENDING for CAMERA_LAB-only — use N/A
        face_status = "N_A"
    elif not face_status:
        face_status = "PENDING"
    guidance = _lab_next_step(run, layers if isinstance(layers, dict) else {})
    return {
        "run_id": run.run_id,
        "nonce": run.nonce,
        "kind": run.kind,
        "camera_id": run.camera_id,
        "state": run.state,
        "profile": run.profile,
        "config_revision": run.config_revision or None,
        "provenance": run.provenance or None,
        "decoded_w": run.decoded_w,
        "decoded_h": run.decoded_h,
        "fps_measured": run.fps_measured,
        "frame_age_ms": run.frame_age_ms,
        "challenge_issued": bool(run.owner_challenge),
        "owner_reviewed_by": run.owner_reviewed_by or None,
        "expires_at": run.expires_at.isoformat() if run.expires_at else None,
        "revoked": bool(run.revoked),
        "evidence_layers": layers,
        "face_validation_status": face_status,
        "review_kind": meta.get("review_kind") or "SINGLE_OPERATOR_ACK",
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "note_vi": run.note_vi,
        **guidance,
    }


@router.post("/{camera_id}/lab-runs", dependencies=[Depends(require_csrf)])
def start_camera_lab_run(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Server-issued lab run (CREATED). PHYSICAL_VERIFIED requires measure→owner→promote."""
    from app.services.lab_run_service import LabRunError, start_lab_run
    from app.services.server_pins import derive_live_pins

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    try:
        pins, _ = derive_live_pins(db, pipeline=state.face_pipeline, store=state.template_store)
        run = start_lab_run(
            db,
            camera_id=camera_id,
            kind=str(body.get("kind") or "CAMERA_LAB"),
            operator=user.username,
            pins=pins,
            profile=str(body.get("profile") or "MAIN"),
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _lab_run_out(run)


@router.post(
    "/{camera_id}/lab-runs/{run_id}/owner-challenge",
    dependencies=[Depends(require_csrf)],
)
def reveal_lab_owner_challenge(
    camera_id: int,
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Reveal one-time challenge to authenticated UI session only — do not log/print."""
    from app.services.lab_run_service import LabRunError, reveal_owner_challenge

    _ = state
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    try:
        return reveal_owner_challenge(
            db, run_id=run_id, camera_id=camera_id, operator=user.username
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc


@router.post("/{camera_id}/lab-runs/{run_id}/measure", dependencies=[Depends(require_csrf)])
def measure_camera_lab_run(
    camera_id: int,
    run_id: str,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Capture DISTINCT CAMERA_LIVE frames — rejects MOCK/stale/duplicate cached frames."""
    from app.services.lab_run_service import LabRunError, measure_live_frames

    _ = user
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    samples = int(body.get("samples") or 5)
    try:
        run = measure_live_frames(
            db,
            run_id=run_id,
            camera_id=camera_id,
            registry=state.camera_registry,
            samples=samples,
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc
    return _lab_run_out(run)


@router.post("/{camera_id}/lab-runs/{run_id}/face-cases", dependencies=[Depends(require_csrf)])
def record_lab_face_case(
    camera_id: int,
    run_id: str,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Server-measured FACE_PILOT case — supervised consent required; no client count PASS."""
    from app.services.lab_run_service import LabRunError, record_face_pilot_case
    from app.services.server_pins import derive_live_pins

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    try:
        pins, gallery = derive_live_pins(
            db, pipeline=state.face_pipeline, store=state.template_store
        )
        pairs = list(getattr(gallery, "pairs", None) or [])
        case = record_face_pilot_case(
            db,
            run_id=run_id,
            camera_id=camera_id,
            registry=state.camera_registry,
            pipeline=state.face_pipeline,
            gallery_pairs=pairs,
            pins=pins,
            truth_label=str(body.get("truth_label") or ""),
            condition=str(body.get("condition") or "DAY"),
            consent_ack_vi=str(body.get("consent_ack_vi") or ""),
            supervised_by=str(body.get("supervised_by") or user.username),
            subject_key=str(body.get("subject_key") or ""),
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "case_id": case.case_id,
        "lab_run_id": case.lab_run_id,
        "truth_label": case.truth_label,
        "pred_label": case.pred_label,
        "outcome": case.outcome,
        "similarity": case.similarity,
        "condition": case.condition,
        "latency_ms": case.latency_ms,
        "native_face_width_px": case.native_face_width_px,
        "lighting_is_operator_claim": True,
        "note_vi": case.note_vi,
        "face_pilot_pass": False,
    }


@router.post("/{camera_id}/lab-runs/{run_id}/owner-review", dependencies=[Depends(require_csrf)])
def owner_review_lab_run(
    camera_id: int,
    run_id: str,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """Single-operator ack after LIVE_MEASURED; FACE_PILOT requires CORRECT outcomes only."""
    from app.services.lab_run_service import LabRunError, owner_review

    _ = state
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    try:
        run = owner_review(
            db,
            run_id=run_id,
            camera_id=camera_id,
            operator=user.username,
            challenge=str(body.get("challenge") or ""),
            ack_vi=str(body.get("ack_vi") or ""),
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc
    return _lab_run_out(run)


@router.post(
    "/{camera_id}/lab-runs/{run_id}/promote-physical", dependencies=[Depends(require_csrf)]
)
def promote_lab_run_physical(
    camera_id: int,
    run_id: str,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """PHYSICAL_VERIFIED only after OWNER_REVIEWED + fresh LIVE recheck (EV11)."""
    from app.services.lab_run_service import LabRunError, promote_physical
    from app.services.server_pins import derive_live_pins

    _ = body
    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    if state.face_pipeline is None or state.template_store is None:
        raise HTTPException(status_code=503, detail="Pipeline chưa sẵn sàng")
    try:
        pins, _ = derive_live_pins(db, pipeline=state.face_pipeline, store=state.template_store)
        ev = promote_physical(
            db,
            run_id=run_id,
            camera_id=camera_id,
            operator=user.username,
            registry=state.camera_registry,
            pins=pins,
        )
    except LabRunError as exc:
        raise _lab_run_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "evidence_id": ev.evidence_id,
        "lab_run_id": ev.lab_run_id,
        "kind": ev.kind,
        "evidence_class": ev.evidence_class,
        "camera_id": camera_id,
        "decoded_measured": {
            "width": ev.decoded_w,
            "height": ev.decoded_h,
            "fps": ev.fps_measured,
        },
        "labeled_known": ev.labeled_known,
        "labeled_unknown": ev.labeled_unknown,
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "note_vi": (
            "PHYSICAL_VERIFIED từ lab run đã owner-review — vẫn cần ký phê duyệt riêng. "
            "Không chứa ảnh/mật khẩu."
        ),
    }


@router.post("/{camera_id}/evidence/record", dependencies=[Depends(require_csrf)])
def record_pilot_evidence(
    camera_id: int,
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
) -> dict:
    """
    Record non-physical evidence only (LIVE_PENDING / UNTRUSTED_IMPORT).
    PHYSICAL_VERIFIED requires lab-run FSM: start → measure → owner-review → promote-physical.
    Client labeled_known/unknown counts alone are rejected for FACE_PILOT physical (EV01/EV11).
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
    if want_class == EVIDENCE_PHYSICAL or want_class == "PHYSICAL_VERIFIED":
        # EV01/EV06/EV11 — health W/H + client label counts are insufficient
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_LAB_RUN_PROMOTE",
                "message_vi": (
                    "PHYSICAL_VERIFIED không ghi trực tiếp qua /evidence/record. "
                    "Dùng lab-runs: measure LIVE tươi → owner-review → promote-physical. "
                    "Số labeled_known/unknown client không đủ cho FACE_PILOT."
                ),
            },
        )
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

    if want_class == EVIDENCE_UNTRUSTED_IMPORT:
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
        "note_vi": (
            "Đã ghi bằng chứng không-PHYSICAL (không chứa ảnh/mật khẩu). "
            "PHYSICAL_VERIFIED cần lab-run FSM trên máy Windows LAN."
        ),
    }


@router.get("/{camera_id}/quality/evidence")
def list_quality_evidence(
    camera_id: int,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[User, Depends(require_permission("PILOT_APPROVE"))],
    kind: str = "CAMERA_LAB",
) -> dict:
    """List redacted PHYSICAL_VERIFIED evidence eligible for HMAC signing (no auto-sign)."""
    from app.services.evidence_store import EVIDENCE_PHYSICAL, list_physical_evidence_for_camera
    from app.services.pilot_approval import verify_active_approval
    from app.services.server_pins import derive_live_pins

    row = db.get(CameraDevice, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy camera")
    kind_u = (kind or "CAMERA_LAB").upper()
    if kind_u not in {"CAMERA_LAB", "FACE_PILOT"}:
        raise HTTPException(status_code=422, detail="kind không hợp lệ")
    pins: dict[str, str] | None = None
    if state.face_pipeline is not None and state.template_store is not None:
        try:
            pins, _gallery = derive_live_pins(
                db, pipeline=state.face_pipeline, store=state.template_store
            )
        except Exception:  # noqa: BLE001
            pins = None
    items = list_physical_evidence_for_camera(
        db, camera_id=camera_id, kind=kind_u, pins=pins, limit=20
    )
    signed = None
    if pins:
        signed_view = verify_active_approval(
            db,
            secret_key=state.settings.secret_key,
            kind=kind_u,
            camera_id=camera_id,
            model_hash_pin=pins.get("model_hash_pin"),
            gallery_revision_pin=pins.get("gallery_revision_pin"),
            threshold_id_pin=pins.get("threshold_id_pin"),
        )
        if signed_view and signed_view.valid:
            signed = {
                "approval_id": signed_view.approval_id,
                "expires_at": (
                    signed_view.expires_at.isoformat() if signed_view.expires_at else None
                ),
                "code": signed_view.code,
            }
    return {
        "schema": "mypc.quality-evidence.v1",
        "camera_id": camera_id,
        "kind": kind_u,
        "evidence_class_filter": EVIDENCE_PHYSICAL,
        "items": items,
        "signed_active": signed,
        "camera_lab_pass": False,
        "physical_verified_ne_signed": True,
        "note_vi": (
            "PHYSICAL_VERIFIED ≠ CAMERA_LAB_SIGNED. Chọn evidence rồi POST /quality/approvals. "
            "Không lộ challenge/cookie/ảnh. FACE_PILOT tách biệt."
        ),
        "actor": user.username,
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


def _camera_delete_blockers(db: Session, camera_id: int) -> dict[str, int]:
    """Historical blockers only — config-only rows may be cascade-cleaned on hard delete."""
    from app.models.entities import (
        AbEvaluationRun,
        CameraLabRun,
        PilotApprovalRecord,
        PilotEvidenceRecord,
        RawObservation,
    )

    counts: dict[str, int] = {
        "raw_observations": int(
            db.scalar(
                select(func.count()).select_from(RawObservation).where(RawObservation.camera_id == camera_id)
            )
            or 0
        ),
        "lab_runs": 0,
        "approvals": 0,
        "ab_runs": 0,
        "evidence_records": 0,
    }
    # Do not swallow count failures as zero — treat query errors as hard blockers
    try:
        counts["lab_runs"] = int(
            db.scalar(select(func.count()).select_from(CameraLabRun).where(CameraLabRun.camera_id == camera_id))
            or 0
        )
        counts["approvals"] = int(
            db.scalar(
                select(func.count())
                .select_from(PilotApprovalRecord)
                .where(PilotApprovalRecord.camera_id == camera_id)
            )
            or 0
        )
        counts["ab_runs"] = int(
            db.scalar(select(func.count()).select_from(AbEvaluationRun).where(AbEvaluationRun.camera_id == camera_id))
            or 0
        )
        counts["evidence_records"] = int(
            db.scalar(
                select(func.count())
                .select_from(PilotEvidenceRecord)
                .where(PilotEvidenceRecord.camera_id == camera_id)
            )
            or 0
        )
    except Exception:
        counts["blocker_query_failed"] = 1
    counts["total"] = int(sum(int(v) for k, v in counts.items() if k != "total"))
    return counts


def _cam_out(r: CameraDevice, state: AppState | None = None, *, detail: bool = False) -> dict:
    runtime = None
    live_decoded = False
    if state is not None and state.camera_registry is not None and not getattr(r, "archived", False):
        try:
            bound = state.camera_registry.get(r.id)
            if bound is not None:
                h = bound.gateway.health()
                extras = getattr(h, "extras", {}) or {}
                live_decoded = bool(extras.get("live_decoded"))
                runtime = {
                    "bound": True,
                    "provenance": h.provenance.value if hasattr(h.provenance, "value") else str(h.provenance),
                    "decoder_status": h.decoder_status.value
                    if hasattr(h.decoder_status, "value")
                    else str(h.decoder_status),
                    "connection_status": extras.get("connection_status") or h.decoder_status.value,
                    "native_width": h.native_width,
                    "native_height": h.native_height,
                    "fps_estimate": h.fps_estimate,
                    "frames_ok": extras.get("frames_ok", 0),
                    "live_decoded": live_decoded,
                    "config_revision": bound.config_revision,
                    "camera_lab_pass": False,
                }
        except Exception:
            runtime = {"bound": False}
    safe_uri = safe_rtsp_uri_for_edit(r.rtsp_url_override or "")
    has_secret = bool(r.secret_ref) and (
        state.secrets.has_secret(r.secret_ref) if state is not None and r.secret_ref else bool(r.secret_ref)
    )
    out = {
        "id": r.id,
        "name": r.name,
        "host": r.host,
        "model": r.model,
        "firmware": r.firmware,
        "has_rtsp_override": bool(r.rtsp_url_override),
        "rtsp_uri_safe": safe_uri,  # editable, no userinfo — never password
        "rtsp_override_redacted": redact_url(r.rtsp_url_override),
        "has_secret": has_secret,
        "credential_saved": has_secret,
        "username_hint": r.username_hint or "",
        "mock_mode": r.mock_mode,
        "enabled": r.enabled,
        "archived": bool(getattr(r, "archived", False)),
        "connection_status": getattr(r, "connection_status", None) or "UNKNOWN",
        "config_revision": getattr(r, "config_revision", "") or "",
        "last_health_status": r.last_health_status,
        "last_health_at": r.last_health_at.isoformat() if r.last_health_at else None,
        "live_verified": live_decoded,
        "runtime": runtime,
        "password": None,  # never serialize
    }
    if detail:
        # ROI summary (no secrets)
        out["note_vi"] = (
            "Mật khẩu không bao giờ trả về API. Ô mật khẩu trống = giữ credential đã lưu. "
            "CONFIG_SAVED ≠ LIVE verified."
        )
    return out

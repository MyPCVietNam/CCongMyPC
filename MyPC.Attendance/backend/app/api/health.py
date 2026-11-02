"""Health and diagnostics endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import APP_NAME, SPEC_VERSION, __version__
from app.api.deps import AppState, get_app_state, get_current_user
from app.core.database import check_integrity

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
def health(state: Annotated[AppState, Depends(get_app_state)]) -> dict:
    # Distinguish MIGRATING/FAIL from READY — console quiet after Alembic ≠ hang
    if getattr(state, "alembic_ok", True) is False and getattr(state, "alembic_error", None):
        phase = "FAIL"
        status = "degraded"
    else:
        phase = "READY"
        status = "ok"
    return {
        "status": status,
        "app": APP_NAME,
        "version": __version__,
        "spec_version": SPEC_VERSION,
        "mock_camera": state.camera.state.mock_mode,
        "camera_fsm": state.camera.state.fsm.value,
        "config_version": state.config_service.active.version,
        "exit_verification_gate": state.config_service.active.exit_verification_gate,
        "app_env": state.settings.app_env,
        "demo_mode": state.settings.demo_mode,
        "startup_phase": phase,
        "alembic_ok": bool(getattr(state, "alembic_ok", True)),
        "alembic_error": getattr(state, "alembic_error", None),
        "data_dir": str(state.settings.data_dir),
        "note_vi": (
            "Nếu console dừng sau Alembic: kiểm tra startup_phase và HTTP /api/v1/health — "
            "không kết luận treo khi listener + HTTP 200."
        ),
    }


@router.get("/api/v1/system/runtime-badge")
def runtime_badge(
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """Server-authoritative env + stream provenance — never imply LIVE from MOCK boot.

    Requires auth. Pending password-change users are denied (not on allowlist) —
    UI only shows this badge after forced change completes.
    """
    _ = user
    provenance = "MOCK"
    camera_id = None
    config_revision = None
    decoded = None
    reg = state.camera_registry
    if reg is not None:
        try:
            health_map = reg.health()
            sources = health_map.get("sources") if isinstance(health_map, dict) else None
            if sources:
                s0 = sources[0]
                provenance = str(s0.get("provenance") or "UNKNOWN")
                camera_id = s0.get("camera_id")
                config_revision = s0.get("config_revision")
                decoded = {
                    "width": s0.get("native_width"),
                    "height": s0.get("native_height"),
                    "fps_estimate": s0.get("fps_estimate"),
                }
        except Exception:  # noqa: BLE001
            provenance = "UNKNOWN"
    else:
        provenance = "MOCK" if state.camera.state.mock_mode else "UNKNOWN"
    # LIVE label only if provenance claims CAMERA_LIVE — still not CAMERA_LAB PASS
    label_vi = {
        "CAMERA_LIVE": "Nguồn LIVE (chưa chứng minh CAMERA_LAB)",
        "MOCK": "Dữ liệu mô phỏng / MOCK",
        "AUTHORIZED_RECORDED": "REPLAY đã ủy quyền",
        "UNKNOWN": "Nguồn chưa xác minh",
    }.get(provenance, f"Nguồn: {provenance}")
    return {
        "schema": "mypc.runtime-badge.v1",
        "app_env": state.settings.app_env,
        "demo_mode": bool(state.settings.demo_mode),
        "stream_provenance": provenance,
        "label_vi": label_vi,
        "camera_id": camera_id,
        "config_revision": config_revision,
        "decoded": decoded,
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "note_vi": (
            "Nhãn MOCK/LIVE lấy từ server. TCP camera ≠ decode LIVE. "
            "CAMERA_LAB/FACE_PILOT vẫn BLOCKED đến khi có bằng chứng vật lý."
        ),
    }


@router.get("/api/v1/system/diagnostics")
def diagnostics(state: Annotated[AppState, Depends(get_app_state)]) -> dict:
    integrity = "n/a"
    try:
        engine = state.session_factory.kw["bind"]  # type: ignore[index]
        integrity = check_integrity(engine)
    except Exception as exc:  # noqa: BLE001
        integrity = f"error:{type(exc).__name__}"

    return {
        "app": APP_NAME,
        "app_version": state.settings.app_version,
        "spec_version": state.settings.spec_version,
        "schema_version": 1,
        "config_version": state.config_service.active.version,
        "config_ack_at": (
            state.config_service.ack_at.isoformat() if state.config_service.ack_at else None
        ),
        "ai_models": (
            state.face_pipeline.status() if state.face_pipeline else {"ready": False}
        ),
        "app_env": state.settings.app_env,
        "demo_mode": state.settings.demo_mode,
        "camera": {
            "fsm": state.camera.state.fsm.value,
            "mock_mode": state.camera.state.mock_mode,
            "model_declared": "CS-H8-R100-1J5WKFL",
            "onvif_listed_from_firmware": "V5.3.8 build 231201+",
            "rtsp_tested": False,
            "camera_lab_pass": False,
            "note_vi": (
                "Tương thích ONVIF theo danh sách hãng không đồng nghĩa đã kiểm chứng "
                "luồng RTSP trên môi trường này."
            ),
        },
        "sqlite_integrity": integrity,
        "gates": {
            "UNIT": "see test report",
            "MOCK_INTEGRATION": "see test report",
            "P00_SECURITY": "see test report",
            "MODEL_INTEGRITY": "see models/manifest.json",
            "CAMERA_LAB_PASS": False,
            "FACE_PILOT_PASS": False,
            "EXIT_VERIFICATION_GATE": state.config_service.active.exit_verification_gate,
            "WINDOWS_RUNTIME": False,
            "WINDOWS_INSTALL_PASS": False,
        },
        "afternoon_window": {
            "start": state.config_service.active.windows.afternoon_recognition_start,
            "end_exclusive": state.config_service.active.windows.afternoon_recognition_end_exclusive,
            "reference": state.config_service.active.windows.afternoon_selection.reference_time,
        },
    }

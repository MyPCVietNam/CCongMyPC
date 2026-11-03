"""Health and diagnostics endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import APP_NAME, SPEC_VERSION, __version__
from app.api.deps import AppState, get_app_state, get_current_user, require_csrf
from app.core.database import check_integrity

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
def health(state: Annotated[AppState, Depends(get_app_state)]) -> dict:
    # Distinguish MIGRATING/FAIL from READY — console quiet after Alembic ≠ hang.
    # Dev/test may recover via create_all after a transient Alembic SQLite race;
    # only mark FAIL when production and migrations did not apply.
    alembic_ok = bool(getattr(state, "alembic_ok", True))
    alembic_error = getattr(state, "alembic_error", None)
    if not alembic_ok and alembic_error and state.settings.is_production():
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
    decoder_status = None
    operationally_ready = False
    reg = state.camera_registry
    if reg is not None:
        try:
            health_map = reg.health()
            sources = health_map.get("sources") if isinstance(health_map, dict) else None
            # Prefer an operationally-ready LIVE source; never imply LIVE from provenance alone (P1-03)
            chosen = None
            if sources:
                for s in sources:
                    if (
                        str(s.get("provenance") or "") == "CAMERA_LIVE"
                        and s.get("operationally_ready")
                        and str(s.get("decoder_status") or "") == "OK"
                    ):
                        chosen = s
                        break
                if chosen is None:
                    chosen = sources[0]
            if chosen is not None:
                provenance = str(chosen.get("provenance") or "UNKNOWN")
                camera_id = chosen.get("camera_id")
                config_revision = chosen.get("config_revision")
                decoder_status = chosen.get("decoder_status")
                operationally_ready = bool(chosen.get("operationally_ready"))
                decoded = {
                    "width": chosen.get("native_width"),
                    "height": chosen.get("native_height"),
                    "fps_estimate": chosen.get("fps_estimate"),
                }
                if provenance == "CAMERA_LIVE" and not (
                    operationally_ready and str(decoder_status or "") == "OK"
                ):
                    # Bound but not healthy — honest badge
                    provenance = "CAMERA_LIVE_NOT_READY"
        except Exception:  # noqa: BLE001
            provenance = "UNKNOWN"
    else:
        provenance = "MOCK" if state.camera.state.mock_mode else "UNKNOWN"
    label_vi = {
        "CAMERA_LIVE": "Nguồn LIVE đã giải mã (chưa CAMERA_LAB_PASS)",
        "CAMERA_LIVE_NOT_READY": "Đã gắn LIVE nhưng decoder chưa sẵn sàng",
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
        "decoder_status": decoder_status,
        "operationally_ready": operationally_ready,
        "decoded": decoded,
        "camera_lab_pass": False,
        "face_pilot_pass": False,
        "note_vi": (
            "Nhãn MOCK/LIVE lấy từ server. Provenance ≠ decoder healthy ≠ CAMERA_LAB_PASS. "
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
        "secret_fs_outbox": {
            "startup_recovery": getattr(state, "secret_fs_recovery", None),
            "pending": __import__(
                "app.services.secret_fs_outbox", fromlist=["list_pending_journals"]
            ).list_pending_journals(state.secrets),
        },
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


@router.post("/api/v1/system/secret-fs-outbox/retry", dependencies=[Depends(require_csrf)])
def retry_secret_fs_outbox(
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """Safely replay durable credential FS journals left after post-commit failures."""
    _ = user
    from app.services.secret_fs_outbox import list_pending_journals, recover_pending_journals

    summary = recover_pending_journals(state.secrets)
    state.secret_fs_recovery = summary  # type: ignore[attr-defined]
    pending = list_pending_journals(state.secrets)
    return {
        "ok": summary.get("journals_failed", 0) == 0 and not pending,
        "recovery": summary,
        "pending": pending,
        "message_vi": (
            "Đã thử phát lại nhật ký credential. "
            "Nếu vẫn còn pending — kiểm tra quyền ACL thư mục secrets."
            if pending
            else "Không còn nhật ký credential chờ xử lý."
        ),
    }

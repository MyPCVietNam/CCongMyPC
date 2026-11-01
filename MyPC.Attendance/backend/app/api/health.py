"""Health and diagnostics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import APP_NAME, SPEC_VERSION, __version__
from app.api.deps import AppState, get_app_state
from app.core.database import check_integrity

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
def health(state: Annotated[AppState, Depends(get_app_state)]) -> dict:
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": __version__,
        "spec_version": SPEC_VERSION,
        "mock_camera": state.camera.state.mock_mode,
        "camera_fsm": state.camera.state.fsm.value,
        "config_version": state.config_service.active.version,
        "exit_verification_gate": state.config_service.active.exit_verification_gate,
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
        "ai_models": {
            "yunet": "PENDING_DOWNLOAD_VERIFY",
            "sface": "PENDING_DOWNLOAD_VERIFY",
        },
        "camera": {
            "fsm": state.camera.state.fsm.value,
            "mock_mode": state.camera.state.mock_mode,
            "model_declared": "CS-H8-R100-1J5WKFL",
            "onvif_listed_from_firmware": "V5.3.8 build 231201+",
            "rtsp_tested": False,
            "camera_lab_pass": False,
            "note_vi": (
                "Tương thích ONVIZ theo danh sách hãng không đồng nghĩa đã kiểm chứng "
                "luồng RTSP trên môi trường này."
            ),
        },
        "sqlite_integrity": integrity,
        "gates": {
            "UNIT": "see test report",
            "MOCK_INTEGRATION": "see test report",
            "CAMERA_LAB_PASS": False,
            "EXIT_VERIFICATION_GATE": state.config_service.active.exit_verification_gate,
            "WINDOWS_INSTALL_PASS": False,
        },
        "afternoon_window": {
            "start": state.config_service.active.windows.afternoon_recognition_start,
            "end_exclusive": state.config_service.active.windows.afternoon_recognition_end_exclusive,
            "reference": state.config_service.active.windows.afternoon_selection.reference_time,
        },
    }

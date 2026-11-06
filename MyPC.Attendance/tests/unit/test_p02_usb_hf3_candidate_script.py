"""Contract tests for P02-USB-HF3 Windows candidate script (text-level)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "scripts" / "windows" / "p02_usb_hf3_candidate_18878.ps1"
DIAG = ROOT / "scripts" / "windows" / "p02_usb_hf3_readonly_diag.py"


def test_hf3_script_modes_and_port():
    text = PS1.read_text(encoding="utf-8")
    assert "-Mode" in text
    for mode in ("Prepare", "Preflight", "Start", "Stop", "Diagnose", "SafeExport"):
        assert mode in text
    assert "18878" in text
    assert "18876" not in text or "18876/18877" in text  # mention only as forbidden
    assert "uvicorn" in text
    assert "MYPC_MODELS_DIR" in text
    assert "MYPC_DATA_DIR" in text
    assert "python -m pip" in text or "-m pip" in text
    assert "p02-usb-hf3-candidate" in text
    # Must verify both ONNX pins via manifest models[]
    assert "face_detection_yunet_2023mar.onnx" in text
    assert "face_recognition_sface_2021dec.onnx" in text
    assert "PIN_MATCH" in text
    assert "Get-ManifestPinMap" in text or "models" in text


def test_hf3_readonly_diag_redacted_keys():
    text = DIAG.read_text(encoding="utf-8")
    for key in (
        "PNP_VIDEO_COUNT",
        "DSHOW_VIDEO_MONIKER_COUNT",
        "VIDEO_DEVICE_PATH_MATCH_COUNT",
        "CAPTURE_MAPPING_VERIFIED",
        "VERIFIED_INDEX",
        "VIDEO_FRAME_RECEIVED",
        "MODEL_PINS_PASS",
    ):
        assert key in text
    assert "password" not in text.lower() or "excluded" in text.lower()


def test_requirements_windows_pins_comtypes():
    req = (ROOT / "backend" / "requirements-windows.txt").read_text(encoding="utf-8")
    assert "comtypes" in req
    assert "SystemDeviceEnum" in req or "ICreateDevEnum" in req

"""Contract tests for P02-USB-HF3 Windows candidate script (text-level)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "scripts" / "windows" / "p02_usb_hf3_candidate_18878.ps1"
DIAG = ROOT / "scripts" / "windows" / "p02_usb_hf3_readonly_diag.py"


def test_hf3_script_modes_and_port():
    text = PS1.read_text(encoding="utf-8")
    assert "-Mode" in text
    for mode in ("Prepare", "Update", "Preflight", "Start", "Stop", "Diagnose", "SafeExport"):
        assert mode in text
    assert "DataDir untouched" in text or "src only" in text.lower()
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
    # Start must require HTTP 200 + status=ok + READY (never FAIL/degraded)
    assert "Test-Hf3HealthStartPass" in text
    assert "startup_phase" in text
    assert "EXIT_LISTENER_OWNERSHIP" in text
    assert "VERIFIED_DESCENDANT" in text
    assert "uvicorn.launch.json" in text
    assert "Resolve-Hf3ListenerOwnership" in text
    assert 'READY|FAIL' not in text  # FAIL must not be Start PASS
    assert "ok|degraded" not in text  # degraded must not be Start PASS
    assert "catch {}" not in text.split('"Start"')[1].split('"Stop"')[0]
    assert "Refusing Start" in text or "EXIT_FOREIGN_LISTENER" in text
    assert "conhost" in text.lower()


def test_hf3_start_stop_share_launch_meta_trust_model():
    text = PS1.read_text(encoding="utf-8-sig")
    assert "Save-Hf3LaunchMeta" in text
    assert "Test-LiveMatchesLaunchMeta" in text
    assert "Stop-VerifiedHf3Identity" in text
    assert "Stop-VerifiedHf3LaunchTree" in text
    assert "listener_creation" in text
    assert "launcher_creation" in text
    assert "session_proof" in text or "sessionProofPid" in text
    assert "EXIT_FOREIGN_LISTENER" in text
    assert "EXIT_STOP_BLOCKED_LEGACY_PID" in text
    assert "Test-Hf3LaunchMetaSchema" in text
    assert "creation-time mismatch" in text or "creation_match" in text
    # No foreach($pid) collision with automatic $PID
    assert not re.search(r"(?i)\bforeach\s*\(\s*\$pid\b", text)
    assert "$venvMarker" not in text
    assert "Split-Hf3WindowsCommandLine" in text
    assert "$CommandLine.IndexOf($backendNorm" not in text
    # Stop no-listener path must not ignore launcher stop result
    stop = text.split('  "Stop" {', 1)[1].split('  "Diagnose" {', 1)[0]
    no_listener = stop.split("# No listener:", 1)[1]
    assert "[void](Stop-VerifiedHf3Identity" not in no_listener
    assert "EXIT_STOP_INCOMPLETE" in no_listener


def test_hf3_update_uses_leaf_rename_and_rollback():
    """PS 5.1 Rename-Item -NewName must be a leaf; Update must validate then rollback."""
    text = PS1.read_text(encoding="utf-8-sig")
    assert not re.search(r"Rename-Item\s+\$srcDir\s+\$backup\b", text)
    assert not re.search(r"Rename-Item\s+\$stageSrc\s+\$srcDir\b", text)
    assert "Rename-Item -LiteralPath $srcDir -NewName $backupLeaf" in text
    assert "Rename-Item -LiteralPath $stageSrc -NewName $srcLeaf" in text
    assert "Split-Path -Path $srcDir -Leaf" in text
    assert "staged backend" in text.lower() or "Find-BackendDir $stageSrc" in text
    assert "rollback" in text.lower()
    assert "Port 18878 in use" in text or "before Update" in text
    assert "DataDir" in text and "venv" in text


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

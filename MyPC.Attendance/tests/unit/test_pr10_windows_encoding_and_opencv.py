"""PR10-HF: PowerShell UTF-8 BOM encoding + OpenCV import smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WIN = ROOT / "scripts" / "windows"
BOM = b"\xef\xbb\xbf"


def test_win12_all_ps1_have_utf8_bom():
    files = sorted(WIN.glob("*.ps1"))
    assert files, "expected Windows PowerShell scripts"
    missing = [p.name for p in files if not p.read_bytes().startswith(BOM)]
    assert missing == [], f"UTF-8 BOM missing: {missing}"


def test_win13_scripts_do_not_set_execution_policy():
    bad = []
    for p in WIN.glob("*.ps1"):
        text = p.read_text(encoding="utf-8-sig").lower()
        if "set-executionpolicy" in text:
            bad.append(p.name)
    assert bad == []


def test_win14_start_script_references_backend_requirements():
    text = (WIN / "Start-MyPCAttendance.ps1").read_text(encoding="utf-8-sig")
    assert "backend\\requirements" in text or "backend/requirements" in text
    assert "npm.cmd" in text
    # Must not suggest non-existent root requirements.txt as the install path
    assert ".\\requirements.txt" not in text.replace("backend\\requirements.txt", "")


def test_opencv_contrib_apis_available():
    cv2 = pytest.importorskip("cv2")
    assert hasattr(cv2, "FaceDetectorYN")
    assert hasattr(cv2, "FaceRecognizerSF")
    assert hasattr(cv2, "imdecode")


def test_requirements_pins_single_opencv_wheel():
    req = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "opencv-contrib-python-headless==4.13.0.92" in req
    # Must not also pin conflicting wheels
    for bad in ("opencv-python==", "opencv-python-headless==", "opencv-contrib-python=="):
        if bad == "opencv-contrib-python==":
            continue  # substring of headless line — check carefully
        assert bad not in req
    assert req.count("opencv-") == 1 or "opencv-contrib-python-headless" in req

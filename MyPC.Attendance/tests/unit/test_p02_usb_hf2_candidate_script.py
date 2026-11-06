"""Text-level contract for HF2 Windows candidate script (not a physical PASS)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "windows" / "p02_usb_hf2_candidate_18878.ps1"


def test_hf2_candidate_script_actually_starts_uvicorn():
    raw = SCRIPT.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM required for Win PS5.1"
    text = raw.decode("utf-8-sig")
    assert "-Mode" in text
    assert "Prepare" in text and "Preflight" in text and "Start" in text and "Export" in text
    assert "uvicorn" in text
    assert "Start-Process" in text
    assert "127.0.0.1" in text and "18878" in text
    assert "MYPC_MODELS_DIR" in text
    assert "MYPC_DATA_DIR" in text or "DATA_DIR" in text
    assert "18876" in text and "18877" in text  # refuse/document
    assert "api/v1/health" in text
    assert "Compress-Archive" in text

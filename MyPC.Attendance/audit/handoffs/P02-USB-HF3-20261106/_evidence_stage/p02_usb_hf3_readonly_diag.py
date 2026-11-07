#!/usr/bin/env python3
"""Read-only P02-USB-HF3 Windows diagnostics (redacted). No admin required.

Never prints raw PnP, DevicePath, frames, credentials, or embeddings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_models(models_dir: Path) -> dict:
    pins = {
        "face_detection_yunet_2023mar.onnx": (
            "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
        ),
        "face_recognition_sface_2021dec.onnx": (
            "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
        ),
    }
    # Prefer repo manifest if discoverable
    for cand in [
        models_dir.parent / "manifest.json",
        models_dir.parent.parent / "manifest.json",
        Path(__file__).resolve().parents[2] / "models" / "manifest.json",
    ]:
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                for m in data.get("models") or []:
                    fn = m.get("filename")
                    sha = m.get("sha256")
                    if fn and sha:
                        pins[fn] = str(sha).lower()
            except Exception:
                pass
            break
    results = {}
    all_ok = True
    for name, exp in pins.items():
        p = models_dir / name
        if not p.is_file():
            results[name] = {"present": False, "pin_match": False}
            all_ok = False
            continue
        got = _sha256(p)
        ok = got == exp.lower()
        results[name] = {
            "present": True,
            "bytes": p.stat().st_size,
            "pin_match": ok,
            # sha only when match (avoid leaking unexpected hash of wrong file in export)
            "sha256": got if ok else "REDACTED_MISMATCH",
        }
        all_ok = all_ok and ok
    return {"MODEL_PINS_PASS": all_ok, "models": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", required=True)
    ap.add_argument(
        "--out-json",
        default="",
        help="Optional path to write redacted JSON (default: stdout only)",
    )
    args = ap.parse_args()
    models_dir = Path(args.models_dir)

    # Ensure backend imports work when PYTHONPATH set by caller
    from app.vision.camera.dshow_com_enum import (  # noqa: WPS433
        BLOCKER_PROGID_DISPATCH_FORBIDDEN,
        enumerate_video_capture_monikers,
    )
    from app.vision.camera.usb_device import usb_redacted_diagnostics  # noqa: WPS433

    # Force a fresh enum for counters
    enumerate_video_capture_monikers()
    usb = usb_redacted_diagnostics()
    models = _check_models(models_dir)

    payload = {
        "PNP_VIDEO_COUNT": usb.get("PNP_VIDEO_COUNT"),
        "DSHOW_ENUM_OK": usb.get("DSHOW_ENUM_OK"),
        "DSHOW_VIDEO_MONIKER_COUNT": usb.get("DSHOW_VIDEO_MONIKER_COUNT"),
        "PROPERTY_BAG_BIND_OK_COUNT": usb.get("PROPERTY_BAG_BIND_OK_COUNT"),
        "FRIENDLY_NAME_READ_OK_COUNT": usb.get("FRIENDLY_NAME_READ_OK_COUNT"),
        "DEVICE_PATH_READ_OK_COUNT": usb.get("DEVICE_PATH_READ_OK_COUNT"),
        "DEVICE_PATH_CANONICAL_OK_COUNT": usb.get("DEVICE_PATH_CANONICAL_OK_COUNT"),
        "VIDEO_DEVICE_PATH_MATCH_COUNT": usb.get("VIDEO_DEVICE_PATH_MATCH_COUNT"),
        "CAPTURE_MAPPING_VERIFIED": usb.get("CAPTURE_MAPPING_VERIFIED"),
        "VERIFIED_INDEX": usb.get("VERIFIED_INDEX"),
        "VIDEO_FRAME_RECEIVED": False,  # diagnose-only; frame proof is separate owner step
        "MODEL_PINS_PASS": models.get("MODEL_PINS_PASS"),
        "DSHOW_BLOCKER_CODE": usb.get("DSHOW_BLOCKER_CODE"),
        "DSHOW_FIRST_BLOCKER_CODE": usb.get("DSHOW_FIRST_BLOCKER_CODE"),
        "DSHOW_FIRST_EXCEPTION_CLASS": usb.get("DSHOW_FIRST_EXCEPTION_CLASS"),
        "DSHOW_HRESULT": usb.get("DSHOW_HRESULT"),
        "COM_RELEASE_WARNING_COUNT": usb.get("COM_RELEASE_WARNING_COUNT"),
        "progid_dispatch_used": False,
        "forbidden_progid_code": BLOCKER_PROGID_DISPATCH_FORBIDDEN,
        "models": models.get("models"),
        "stage_notes": usb.get("stage_notes"),
        "gates_blocked": [
            "USB_WINDOWS_PHYSICAL",
            "USB_STABILITY_30_MIN",
            "USB_CAMERA_LAB_OWNER_SIGN",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_READY",
        ],
        "note_vi": (
            "Phân biệt: ENUM_OK nhưng BIND_TO_STORAGE_FAILED / FRIENDLY_NAME_READ_FAILED / "
            "DEVICE_PATH_READ_FAILED / DEVICE_PATH_MISSING_FROM_DRIVER / identity mismatch."
        ),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    out = args.out_json
    if not out:
        # Default under models parent logs if MYPC candidate layout
        cand = models_dir.parent.parent / "logs" / "diag-redacted.json"
        try:
            cand.parent.mkdir(parents=True, exist_ok=True)
            cand.write_text(text + "\n", encoding="utf-8")
        except Exception:
            pass
    else:
        Path(out).write_text(text + "\n", encoding="utf-8")

    # Nonzero if mapping not verified — honest fail for owner automation
    if not payload.get("CAPTURE_MAPPING_VERIFIED"):
        return 2
    if not payload.get("MODEL_PINS_PASS"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

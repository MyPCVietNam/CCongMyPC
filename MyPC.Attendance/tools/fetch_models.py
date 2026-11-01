#!/usr/bin/env python3
"""
Download or verify OpenCV Zoo YuNet + SFace weights.

Usage:
  python tools/fetch_models.py --download   # requires network
  python tools/fetch_models.py --import-dir /path/to/onnx
  python tools/fetch_models.py --verify

Never invents checksums: records actual SHA256 after bytes are present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models" / "manifest.json"
WEIGHTS = ROOT / "models" / "weights"

# Official opencv_zoo raw paths (pin by updating URL when locking a commit)
MODELS = [
    {
        "id": "yunet_2023mar",
        "filename": "face_detection_yunet_2023mar.onnx",
        "license": "MIT",
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    },
    {
        "id": "sface_2021dec",
        "filename": "face_recognition_sface_2021dec.onnx",
        "license": "Apache-2.0",
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def update_manifest(entries: list[dict]) -> None:
    payload = {
        "models": entries,
        "rejected_models": [
            {
                "id": "insightface_buffalo_l",
                "reason": "Requires separate commercial license for many deployments",
            }
        ],
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--import-dir", type=Path, default=None)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    WEIGHTS.mkdir(parents=True, exist_ok=True)

    entries = []
    for m in MODELS:
        dest = WEIGHTS / m["filename"]
        if args.download:
            print(f"Downloading {m['url']} ...")
            try:
                urllib.request.urlretrieve(m["url"], dest)
            except Exception as exc:
                print(f"DOWNLOAD_FAILED {m['id']}: {exc}", file=sys.stderr)
                entries.append({**m, "sha256": "PENDING_DOWNLOAD_VERIFY", "bundled": False, "bytes": 0})
                continue
        elif args.import_dir:
            src = args.import_dir / m["filename"]
            if not src.exists():
                print(f"MISSING {src}", file=sys.stderr)
                entries.append({**m, "sha256": "PENDING_DOWNLOAD_VERIFY", "bundled": False, "bytes": 0})
                continue
            dest.write_bytes(src.read_bytes())

        if dest.exists():
            digest = sha256(dest)
            entries.append(
                {
                    **m,
                    "sha256": digest,
                    "bytes": dest.stat().st_size,
                    "bundled_in_repo": False,
                    "local_path": str(dest.relative_to(ROOT)),
                    "verified": True,
                }
            )
            print(f"OK {m['id']} sha256={digest} bytes={dest.stat().st_size}")
        else:
            entries.append({**m, "sha256": "PENDING_DOWNLOAD_VERIFY", "bundled": False, "bytes": 0, "verified": False})
            print(f"ABSENT {m['id']}")

    if args.download or args.import_dir or args.verify:
        update_manifest(entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

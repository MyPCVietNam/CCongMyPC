"""Sanitize enrollment session progress JSON — never persist biometric vectors."""

from __future__ import annotations

import json
import math
import re
from typing import Any

# Keys that must never appear in persisted progress_json
FORBIDDEN_PROGRESS_KEYS = {
    "face_embeddings",
    "embeddings",
    "embedding",
    "vectors",
    "vector",
    "template",
    "raw_embedding",
    "probe",
    "password",
    "camera_password",
    "rtsp_url",
    "secret",
}

# Heuristic: long float arrays look like embeddings
_FLOAT_RE = re.compile(r"-?\d+\.\d+")


def scrub_progress(progress: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy safe to persist: slots, sample IDs, scores, hashes, announcements."""
    src = progress or {}
    out: dict[str, Any] = {
        "completed_slots": list(src.get("completed_slots") or []),
        "samples": dict(src.get("samples") or {}),
        "frame_hashes": list(src.get("frame_hashes") or [])[-50:],
        "announcements": list(src.get("announcements") or [])[-20:],
        "quality_scores": dict(src.get("quality_scores") or {}),
        "capture_origin": src.get("capture_origin"),
        "algorithm_backend": src.get("algorithm_backend"),
        "testing_mode": bool(src.get("testing_mode", False)),
        "model_id": src.get("model_id"),
        "model_hash": src.get("model_hash"),
    }
    # Drop any forbidden leftovers explicitly
    for k in list(out.keys()):
        if k in FORBIDDEN_PROGRESS_KEYS:
            out.pop(k, None)
    return {k: v for k, v in out.items() if v is not None and v != {} and v != []}


def progress_contains_forbidden(progress_json: str | dict | None) -> list[str]:
    """Detect plaintext embedding leakage patterns for tests/cleanup."""
    findings: list[str] = []
    if progress_json is None:
        return findings
    if isinstance(progress_json, dict):
        raw = json.dumps(progress_json, ensure_ascii=False)
        data = progress_json
    else:
        raw = str(progress_json)
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        return findings
    for key in FORBIDDEN_PROGRESS_KEYS:
        if key in data:
            findings.append(f"forbidden_key:{key}")
    # Nested face_embeddings style
    for k, v in data.items():
        if isinstance(v, dict) and any(isinstance(x, list) and _looks_like_embedding(x) for x in v.values()):
            findings.append(f"embedding_like_under:{k}")
        if isinstance(v, list) and _looks_like_embedding(v):
            findings.append(f"embedding_like_list:{k}")
    # Dense float dump in raw text
    floats = _FLOAT_RE.findall(raw)
    if len(floats) >= 64:
        findings.append("dense_float_payload")
    return findings


def _looks_like_embedding(arr: list) -> bool:
    if len(arr) < 32:
        return False
    nums = [x for x in arr if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if len(nums) < 32:
        return False
    # embeddings are typically ~128 floats in [-1,1]
    finite = [float(x) for x in nums if math.isfinite(float(x))]
    if len(finite) < 32:
        return False
    return max(abs(x) for x in finite) <= 5.0

"""Real paired ORIGINAL vs ENHANCED recognition when weights usable — else BLOCKED_MODEL."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.vision.faces.adaptive_quality import trial_enhance_copy
from app.vision.faces.types import InferenceMode, MatchOutcome


def run_paired_recognition(
    bgr_original: np.ndarray,
    *,
    pipeline: Any,
    gallery: list[tuple[int, np.ndarray]],
    identity_fixture_key: str | None = None,
) -> dict[str, Any]:
    """
    Same source pixels → ORIGINAL path and ENHANCED copy through FacePipeline.verify.
    Public metrics only; never auto-enables AUTO_VALIDATED.
    """
    status = pipeline.status()
    mode = status.get("inference_mode")
    weights = status.get("weights_bundled") or {}
    if mode == InferenceMode.REAL.value and not (weights.get("yunet") and weights.get("sface")):
        return {
            "status": "BLOCKED_MODEL",
            "can_auto_enable_enhancement": False,
            "note_vi": "Thiếu trọng số YuNet/SFace — không tạo metrics giả.",
        }

    orig_pixels = np.array(bgr_original, copy=True, order="C")
    trial = trial_enhance_copy(bgr_original)
    enh_pixels = (
        np.array(trial.image, copy=True, order="C")
        if trial.status == "SHADOW_CANDIDATE_ONLY"
        else orig_pixels.copy()
    )

    def _run(img: np.ndarray, label: str) -> dict[str, Any]:
        started = time.perf_counter()
        result = pipeline.verify(img, gallery, identity_fixture_key=identity_fixture_key)
        pred: str
        if result.outcome == MatchOutcome.MATCH and result.employee_id is not None:
            pred = str(result.employee_id)
        elif result.outcome == MatchOutcome.AMBIGUOUS:
            pred = "AMBIGUOUS"
        elif result.outcome == MatchOutcome.UNKNOWN:
            pred = "UNKNOWN"
        else:
            pred = result.outcome.value
        q = result.quality
        return {
            "path": label,
            "pred": pred,
            "outcome": result.outcome.value,
            "similarity": result.similarity,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "native_face_width_px": q.face_width_px if q else None,
            "inter_eye_native_px": q.inter_eye_px if q else None,
            "inference_mode": result.inference_mode,
        }

    original = _run(orig_pixels, "ORIGINAL")
    enhanced = _run(enh_pixels, "ENHANCED")
    blockers: list[str] = []
    if (
        original["pred"] not in {"UNKNOWN", "AMBIGUOUS", "NO_FACE", "LOW_QUALITY", "NOT_READY"}
        and enhanced["pred"]
        not in {"UNKNOWN", "AMBIGUOUS", "NO_FACE", "LOW_QUALITY", "NOT_READY", original["pred"]}
    ):
        blockers.append("HARD_REGRESSION_OR_FALSE_ACCEPT")
    if original["pred"] in {"UNKNOWN", "AMBIGUOUS"} and enhanced["pred"] not in {
        "UNKNOWN",
        "AMBIGUOUS",
        "NO_FACE",
        "LOW_QUALITY",
        "NOT_READY",
    }:
        blockers.append("UNKNOWN_TO_KNOWN_ON_ENHANCE")

    return {
        "status": "OK" if mode else "BLOCKED_MODEL",
        "original": original,
        "enhanced": enhanced,
        "enhancement_status": trial.status,
        "applied_methods": list(trial.applied_methods),
        "blockers": blockers,
        "can_auto_enable_enhancement": False,
        "inference_mode": mode,
        "note_vi": (
            "So sánh nhận diện gốc/xử lý trên cùng khung hình. "
            "Không tự bật AUTO_VALIDATED; UNKNOWN→known trên enhanced là blocker."
        ),
    }

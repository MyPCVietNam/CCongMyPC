"""Conservative luminance-only enhancement on BGR *copies* — shadow A/B only by default."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np


class AutoEnhanceMode(str, Enum):
    OFF = "OFF"
    AUTO_TEST_ONLY = "AUTO_TEST_ONLY"  # safe default: original official, enhanced shadow
    AUTO_VALIDATED = "AUTO_VALIDATED"  # only after LIVE held-out signoff
    AUTO_REVERTED = "AUTO_REVERTED"


@dataclass(frozen=True)
class CandidateResult:
    image: np.ndarray
    applied_methods: tuple[str, ...]
    quality_flags: tuple[str, ...]
    processing_ms: float
    status: str


def _quality_flags(image: np.ndarray) -> tuple[float, float, float, float]:
    import cv2

    y = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[:, :, 0]
    mean = float(np.mean(y))
    p5, p95 = (float(v) for v in np.percentile(y, [5, 95]))
    focus = float(cv2.Laplacian(y, cv2.CV_64F).var())
    return mean, p5, p95, focus


def trial_enhance_copy(original_bgr: np.ndarray, *, max_processing_ms: float = 200.0) -> CandidateResult:
    import cv2

    started = time.perf_counter()
    if (
        not isinstance(original_bgr, np.ndarray)
        or original_bgr.dtype != np.uint8
        or original_bgr.ndim != 3
        or original_bgr.shape[2] != 3
    ):
        raise ValueError("expected uint8 HxWx3 BGR ndarray")
    if original_bgr.shape[0] < 24 or original_bgr.shape[1] < 24 or original_bgr.size > 3 * 8192 * 8192:
        raise ValueError("unreasonable trial input shape")
    original_copy = np.array(original_bgr, copy=True, order="C")
    candidate = original_copy.copy()
    mean, p5, p95, focus = _quality_flags(original_copy)
    flags: list[str] = []
    methods: list[str] = []
    if p95 <= 12:
        flags.append("EXTREME_DARKNESS_RECAPTURE_REQUIRED")
        return CandidateResult(candidate, (), tuple(flags), (time.perf_counter() - started) * 1000, "REJECTED")
    if p5 >= 245:
        flags.append("EXTREME_OVEREXPOSURE_RECAPTURE_REQUIRED")
        return CandidateResult(candidate, (), tuple(flags), (time.perf_counter() - started) * 1000, "REJECTED")
    if focus < 2.0:
        flags.append("POSSIBLE_BLUR_RECAPTURE_RECOMMENDED")
        return CandidateResult(candidate, (), tuple(flags), (time.perf_counter() - started) * 1000, "REJECTED")

    if mean < 82:
        ycc = cv2.cvtColor(candidate, cv2.COLOR_BGR2YCrCb)
        ycc[:, :, 0] = cv2.LUT(
            ycc[:, :, 0], np.round((np.arange(256) / 255.0) ** 0.82 * 255).astype(np.uint8)
        )
        candidate = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
        methods.append("GAMMA_LUMA_MILD_0_82")
    if (p95 - p5) < 75 and mean < 190:
        ycc = cv2.cvtColor(candidate, cv2.COLOR_BGR2YCrCb)
        clahe = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(8, 8))
        ycc[:, :, 0] = clahe.apply(ycc[:, :, 0])
        candidate = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
        methods.append("CLAHE_LUMA_MILD_1_4")
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > max_processing_ms:
        flags.append("PROCESSING_BUDGET_EXCEEDED")
        return CandidateResult(original_copy, (), tuple(flags), elapsed_ms, "FALLBACK_ORIGINAL")
    return CandidateResult(candidate, tuple(methods), tuple(flags), elapsed_ms, "SHADOW_CANDIDATE_ONLY")


def effective_auto_mode(requested: str, *, validated: bool = False, reverted: bool = False) -> AutoEnhanceMode:
    if reverted:
        return AutoEnhanceMode.AUTO_REVERTED
    req = (requested or "OFF").upper()
    if req in {"OFF", "FALSE", "0"}:
        return AutoEnhanceMode.OFF
    if req in {"AUTO", "AUTO_TEST_ONLY", "TỰ ĐỘNG", "TU_DONG"}:
        if validated:
            return AutoEnhanceMode.AUTO_VALIDATED
        return AutoEnhanceMode.AUTO_TEST_ONLY
    if req == "AUTO_VALIDATED":
        return AutoEnhanceMode.AUTO_VALIDATED if validated else AutoEnhanceMode.AUTO_TEST_ONLY
    return AutoEnhanceMode.OFF

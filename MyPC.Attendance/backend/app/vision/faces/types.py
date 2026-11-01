"""Shared face pipeline types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class MatchOutcome(str, Enum):
    MATCH = "MATCH"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_QUALITY = "LOW_QUALITY"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    NO_FACE = "NO_FACE"
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    REPLAY_SUSPECTED = "REPLAY_SUSPECTED"
    NOT_READY = "NOT_READY"


class InferenceMode(str, Enum):
    REAL = "REAL"  # must use genuine YuNet+SFace; fail closed
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"  # CI/demo only


@dataclass(slots=True)
class FaceBox:
    x: int
    y: int
    w: int
    h: int
    score: float = 1.0
    landmarks: list[tuple[float, float]] = field(default_factory=list)
    # Full YuNet detection row for FaceRecognizerSF.alignCrop (x,y,w,h + 5 landmarks + score)
    yunet_row: np.ndarray | None = None

    @property
    def inter_eye_px(self) -> float:
        if len(self.landmarks) < 2:
            return 0.0
        (x1, y1), (x2, y2) = self.landmarks[0], self.landmarks[1]
        return float(np.hypot(x1 - x2, y1 - y2))


@dataclass(slots=True)
class PoseEstimate:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    slot_hint: str  # FACE_FRONT | FACE_LEFT | FACE_RIGHT | UNKNOWN
    confidence: float


@dataclass(slots=True)
class QualityReport:
    ok: bool
    score: float
    face_width_px: int
    inter_eye_px: float
    blur_score: float
    laplacian_var: float
    pose: PoseEstimate | None
    hard_fail: bool
    reasons_vi: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationResult:
    outcome: MatchOutcome
    employee_id: int | None
    similarity: float
    second_best_similarity: float
    message_vi: str
    quality: QualityReport | None = None
    model_id: str = ""
    threshold: float = 0.0
    inference_mode: str = ""

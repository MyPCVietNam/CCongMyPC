"""Shared face pipeline types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass(slots=True)
class FaceBox:
    x: int
    y: int
    w: int
    h: int
    score: float = 1.0
    landmarks: list[tuple[float, float]] = field(default_factory=list)


@dataclass(slots=True)
class QualityReport:
    ok: bool
    score: float
    face_width_px: int
    blur_score: float
    reasons_vi: list[str] = field(default_factory=list)
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

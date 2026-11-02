"""PR6 follow-up P1: paired inference honest gallery/model statuses."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.vision.faces.paired_inference import run_paired_recognition
from app.vision.faces.types import InferenceMode


class _Pipe:
    def __init__(self, mode: str, weights_ok: bool = True):
        self._mode = mode
        self._weights = {"yunet": weights_ok, "sface": weights_ok}

    def status(self):
        return {
            "inference_mode": self._mode,
            "weights_bundled": self._weights,
        }

    def verify(self, img, gallery, identity_fixture_key=None):
        from app.vision.faces.types import MatchOutcome

        return SimpleNamespace(
            outcome=MatchOutcome.UNKNOWN,
            employee_id=None,
            similarity=0.0,
            quality=None,
            inference_mode=self._mode,
        )


def test_empty_gallery_blocked_when_real_model():
    img = np.zeros((48, 48, 3), dtype=np.uint8)
    out = run_paired_recognition(img, pipeline=_Pipe(InferenceMode.REAL.value), gallery=[])
    assert out["status"] == "BLOCKED_GALLERY"
    assert out["can_auto_enable_enhancement"] is False


def test_demo_synthetic_never_ok():
    img = np.zeros((48, 48, 3), dtype=np.uint8)
    gal = [(1, np.ones(128, dtype=np.float32))]
    out = run_paired_recognition(
        img, pipeline=_Pipe(InferenceMode.SYNTHETIC_FIXTURE.value), gallery=gal
    )
    assert out["status"] == "DEMO_SYNTHETIC"
    assert out["can_auto_enable_enhancement"] is False


def test_blocked_model_missing_weights():
    img = np.zeros((48, 48, 3), dtype=np.uint8)
    out = run_paired_recognition(
        img, pipeline=_Pipe(InferenceMode.REAL.value, weights_ok=False), gallery=[(1, np.ones(4))]
    )
    assert out["status"] == "BLOCKED_MODEL"


def test_real_validation_with_gallery():
    img = np.full((64, 64, 3), 80, dtype=np.uint8)
    gal = [(9, np.ones(128, dtype=np.float32))]
    out = run_paired_recognition(img, pipeline=_Pipe(InferenceMode.REAL.value), gallery=gal)
    assert out["status"] == "REAL_VALIDATION"
    assert out["gallery_count"] == 1
    assert out["can_auto_enable_enhancement"] is False

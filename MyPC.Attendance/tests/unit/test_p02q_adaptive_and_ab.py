"""P02Q adaptive enhance + paired A/B evaluator — UNIT_SYNTHETIC."""

from __future__ import annotations

import numpy as np
import pytest

from app.vision.faces.adaptive_quality import AutoEnhanceMode, effective_auto_mode, trial_enhance_copy
from app.vision.faces.paired_ab import EvaluationInputError, evaluate_pairs


def test_extreme_darkness_rejected():
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    r = trial_enhance_copy(img)
    assert r.status == "REJECTED"
    assert "EXTREME_DARKNESS" in r.quality_flags[0]


def test_auto_mode_never_validates_without_flag():
    assert effective_auto_mode("AUTO") == AutoEnhanceMode.AUTO_TEST_ONLY
    assert effective_auto_mode("TỰ ĐỘNG") == AutoEnhanceMode.AUTO_TEST_ONLY
    assert effective_auto_mode("AUTO_VALIDATED", validated=False) == AutoEnhanceMode.AUTO_TEST_ONLY
    assert effective_auto_mode("AUTO", validated=True) == AutoEnhanceMode.AUTO_VALIDATED
    assert effective_auto_mode("AUTO", reverted=True) == AutoEnhanceMode.AUTO_REVERTED


def _pair(**kwargs):
    base = {
        "case_id": "c1",
        "frame_id": "f1",
        "source": "MOCK",
        "condition": "DAY",
        "truth_id": "E1",
        "original_pred": "E1",
        "enhanced_pred": "E1",
        "original_latency_ms": "10",
        "enhanced_latency_ms": "12",
        "native_face_width_px": "160",
        "model_hash": "m1",
        "gallery_revision": "g1",
        "threshold_id": "t1",
    }
    base.update(kwargs)
    return base


def test_ab_blocks_false_accept_and_never_auto_enables():
    rows = [
        _pair(case_id="1", frame_id="a", truth_id="UNKNOWN", original_pred="UNKNOWN", enhanced_pred="E9"),
        _pair(case_id="2", frame_id="b", truth_id="E1", original_pred="E1", enhanced_pred="E2"),
    ]
    result = evaluate_pairs(rows)
    assert result["can_auto_enable_enhancement"] is False
    assert "HARD_REGRESSION_OR_FALSE_ACCEPT" in result["blockers"]
    assert "NO_LIVE_SAMPLES" in result["blockers"]
    assert "NO_OWNER_LIVE_APPROVAL" in result["blockers"]


def test_ab_mock_only_insufficient():
    rows = [_pair()]
    result = evaluate_pairs(rows)
    assert result["can_auto_enable_enhancement"] is False
    assert "MOCK_ONLY_INSUFFICIENT" in result["blockers"]


def test_ab_rejects_duplicate_and_mixed_versions():
    with pytest.raises(EvaluationInputError):
        evaluate_pairs([_pair(), _pair()])
    with pytest.raises(EvaluationInputError):
        evaluate_pairs([_pair(), _pair(case_id="x", frame_id="y", model_hash="other")])

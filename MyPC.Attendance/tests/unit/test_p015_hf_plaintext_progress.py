"""P01.5-HF: progress_json must never store raw face embeddings."""

from __future__ import annotations

import json

import numpy as np

from app.services.progress_sanitize import progress_contains_forbidden, scrub_progress


def test_scrub_removes_face_embeddings():
    dirty = {
        "completed_slots": ["FACE_FRONT"],
        "face_embeddings": {"FACE_FRONT": np.zeros(128).tolist()},
        "samples": {"FACE_FRONT": "abc"},
        "password": "secret",
    }
    clean = scrub_progress(dirty)
    assert "face_embeddings" not in clean
    assert "password" not in clean
    assert clean["completed_slots"] == ["FACE_FRONT"]
    assert not progress_contains_forbidden(clean)


def test_detect_dense_float_payload():
    payload = {"oops": list(np.linspace(-1, 1, 128))}
    findings = progress_contains_forbidden(payload)
    assert findings

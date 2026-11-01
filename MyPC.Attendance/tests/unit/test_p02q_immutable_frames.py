"""P02Q immutable BGR original — UNIT_SYNTHETIC."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from app.vision.camera.gateway import MockFrameGateway
from app.vision.camera.registry import CameraSourceRegistry
from app.vision.camera.gateway import StreamProvenance
from app.vision.faces.adaptive_quality import trial_enhance_copy


def _sha(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def test_sealed_frame_rejects_inplace_write():
    gw = MockFrameGateway(camera_id="1", width=64, height=48)
    gw.start()
    fr = gw.get_latest_frame()
    assert fr is not None
    assert fr.pixel_sha256 == _sha(fr.bgr)
    with pytest.raises(ValueError):
        fr.bgr[0, 0, 0] = 255
    # clone is writable and must not alias
    clone = fr.clone_pixels()
    clone[:] = 1
    assert _sha(fr.bgr) == fr.pixel_sha256
    gw.stop()


def test_enhance_does_not_mutate_original():
    gw = MockFrameGateway(camera_id="2", width=128, height=96)
    gw.start()
    fr = gw.get_latest_frame()
    assert fr is not None
    before = fr.pixel_sha256
    owned = fr.clone_pixels()
    trial_enhance_copy(owned)
    assert _sha(fr.bgr) == before
    gw.stop()


def test_registry_revision_matches_frame():
    reg = CameraSourceRegistry()
    gw = MockFrameGateway(camera_id="9", width=80, height=60)
    gw.start()
    bound = reg.bind(9, gw, provenance=StreamProvenance.MOCK, profile="MOCK")
    fr = gw.get_latest_frame()
    assert fr is not None
    assert fr.config_revision == bound.config_revision
    # Cross-camera isolation: camera 9 frame not served as 10
    with pytest.raises(LookupError):
        reg.get_frame(10, allow_mock=True)
    reg.shutdown_all()

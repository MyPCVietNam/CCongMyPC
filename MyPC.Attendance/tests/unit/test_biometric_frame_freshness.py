"""P0-2: biometric paths must not reuse good frames during decoder degradation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import numpy as np
import pytest

from app.vision.camera.gateway import (
    CameraFrame,
    ClockTrust,
    DecoderStatus,
    GatewayHealth,
    LiveRTSPGateway,
    StreamProvenance,
)
from app.vision.camera.registry import CameraSourceRegistry, FrameAccessError


def _ok_frame(camera_id: str = "1", frame_id: str = "f-ok", *, mono: float = 10.0) -> CameraFrame:
    img = np.full((48, 64, 3), 100, dtype=np.uint8)
    img[10:20, 10:20] = 200
    now = datetime.now(timezone.utc)
    return CameraFrame.from_bgr(
        img,
        frame_id=frame_id,
        camera_id=camera_id,
        capture_time_utc=now,
        receive_time_utc=now,
        provenance=StreamProvenance.CAMERA_LIVE,
        decoder_status=DecoderStatus.OK,
        receive_monotonic=mono,
        integrity_ok=True,
        config_revision="rev-1",
        clock_trust=ClockTrust.SERVER_RECEIVE,
    )


def test_get_latest_good_none_while_degraded():
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="1")
    fr = _ok_frame()
    with gw._lock:
        gw._latest_good = fr
        gw._status = DecoderStatus.DEGRADED
    assert gw.get_latest_good_frame() is None


def test_biometric_rejects_after_corruption_clears_good():
    reg = CameraSourceRegistry()
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="7")
    gw.config_revision = "rev-1"
    fr = _ok_frame("7", "f1")
    with gw._lock:
        gw._latest = fr
        gw._latest_good = fr
        gw._status = DecoderStatus.OK
        gw._frames_ok = 5
        gw._native = (64, 48)

    bound = reg.bind(7, gw, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN")
    bound.config_revision = "rev-1"
    gw.config_revision = "rev-1"

    # Healthy path works once
    b, got = reg.get_frame(7, for_biometric=True, require_live=True, max_age_s=30)
    assert got.frame_id == "f1"

    # Corrupt / degrade — clear good buffer
    with gw._lock:
        gw._status = DecoderStatus.DEGRADED
        gw._latest_good = None
    with pytest.raises(FrameAccessError) as ei:
        reg.get_frame(7, for_biometric=True, require_live=True, max_age_s=30)
    assert ei.value.code in {"DECODER_UNHEALTHY", "DECODER_NOT_READY", "NO_FRAME"}


def test_biometric_rejects_duplicate_frame_id():
    reg = CameraSourceRegistry()
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="3")
    fr = _ok_frame("3", "same-id")
    with gw._lock:
        gw._latest = fr
        gw._latest_good = fr
        gw._status = DecoderStatus.OK
        gw._frames_ok = 2
        gw._native = (64, 48)
    bound = reg.bind(3, gw, provenance=StreamProvenance.CAMERA_LIVE)
    bound.config_revision = fr.config_revision
    gw.config_revision = fr.config_revision

    reg.get_frame(3, for_biometric=True, require_live=True, max_age_s=30)
    with pytest.raises(FrameAccessError) as ei:
        reg.get_frame(3, for_biometric=True, require_live=True, max_age_s=30)
    assert ei.value.code == "DUPLICATE_FRAME_ID"


def test_biometric_cannot_bypass_integrity_flag():
    reg = CameraSourceRegistry()
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="4")
    fr = _ok_frame("4", "f2")
    # Force integrity_ok False on latest
    bad = CameraFrame(
        frame_id=fr.frame_id,
        camera_id=fr.camera_id,
        width=fr.width,
        height=fr.height,
        capture_time_utc=fr.capture_time_utc,
        receive_time_utc=fr.receive_time_utc,
        provenance=fr.provenance,
        decoder_status=DecoderStatus.OK,
        _pixels=fr._pixels,
        config_revision=fr.config_revision,
        clock_trust=fr.clock_trust,
        pixel_sha256=fr.pixel_sha256,
        receive_monotonic=fr.receive_monotonic,
        integrity_ok=False,
    )
    with gw._lock:
        gw._latest = bad
        gw._latest_good = None
        gw._status = DecoderStatus.OK
        gw._frames_ok = 1
        gw._native = (64, 48)
    bound = reg.bind(4, gw, provenance=StreamProvenance.CAMERA_LIVE)
    bound.config_revision = bad.config_revision
    gw.config_revision = bad.config_revision
    # Even if caller tries require_integrity=False, for_biometric forces integrity
    with pytest.raises(FrameAccessError):
        reg.get_frame(
            4,
            for_biometric=True,
            require_live=True,
            require_integrity=False,
            max_age_s=30,
        )


def test_biometric_rejects_stopped_decoder_even_if_good_cached():
    reg = CameraSourceRegistry()
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="5")
    fr = _ok_frame("5", "cached")
    with gw._lock:
        gw._latest_good = fr
        gw._latest = fr
        gw._status = DecoderStatus.STOPPED
        gw._frames_ok = 9
        gw._native = (64, 48)
    bound = reg.bind(5, gw, provenance=StreamProvenance.CAMERA_LIVE)
    bound.config_revision = fr.config_revision
    gw.config_revision = fr.config_revision
    with pytest.raises(FrameAccessError) as ei:
        reg.get_frame(5, for_biometric=True, require_live=True, max_age_s=30)
    assert ei.value.code in {"DECODER_UNHEALTHY", "DECODER_NOT_READY"}

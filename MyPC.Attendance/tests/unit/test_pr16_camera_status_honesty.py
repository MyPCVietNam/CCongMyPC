"""PR16: handshake ≠ LIVE; corrupt backoff; telemetry honesty."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import numpy as np
import pytest

from app.vision.camera.gateway import DecoderStatus, LiveRTSPGateway, frame_looks_corrupt


def test_frame_looks_corrupt_rejects_black_slab():
    black = np.zeros((64, 64, 3), dtype=np.uint8)
    assert frame_looks_corrupt(black) is True
    noisy = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    assert frame_looks_corrupt(noisy) is False


def test_get_latest_frame_marks_stale_while_reconnecting():
    gw = LiveRTSPGateway("rtsp://192.0.2.1:554/ch1/main", camera_id="t1", stale_after_s=30.0)
    # Inject a synthetic OK frame then flip gateway status
    import uuid
    from app.vision.camera.gateway import CameraFrame, ClockTrust, StreamProvenance

    fr = CameraFrame.from_bgr(
        np.random.randint(0, 255, (48, 48, 3), dtype=np.uint8),
        frame_id=str(uuid.uuid4()),
        camera_id="t1",
        capture_time_utc=datetime.now(timezone.utc),
        receive_time_utc=datetime.now(timezone.utc),
        provenance=StreamProvenance.CAMERA_LIVE,
        decoder_status=DecoderStatus.OK,
    )
    with gw._lock:
        gw._latest = fr
        gw._status = DecoderStatus.RECONNECTING
    out = gw.get_latest_frame()
    assert out is not None
    assert out.decoder_status == DecoderStatus.STALE


def test_health_marks_native_ffmpeg_unavailable():
    gw = LiveRTSPGateway("rtsp://192.0.2.1:554/ch1/main", camera_id="t2")
    h = gw.health()
    assert h.extras.get("native_decoder_error_category") == "UNAVAILABLE"
    assert h.extras.get("hevc_ref_events_meaning") == "image_stat_heuristic_only"
    assert "suspected_corrupt_frames" in h.extras


def test_classify_rtsp_status_auth_and_404():
    from app.vision.camera.rtsp_probe import _classify_rtsp_status

    code, _ = _classify_rtsp_status("RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Digest")
    assert code == "AUTH_FAILED"
    code, _ = _classify_rtsp_status("RTSP/1.0 404 Not Found\r\n")
    assert code == "STREAM_NOT_FOUND"
    code, _ = _classify_rtsp_status("")
    assert code == "UNKNOWN"

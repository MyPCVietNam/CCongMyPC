"""P02Q ffprobe sanitizer + gateway telemetry semantics — UNIT_SYNTHETIC."""

from __future__ import annotations

import time

from app.vision.camera.ffprobe_allowlist import sanitize_ffprobe
from app.vision.camera.gateway import ClockTrust, DecoderStatus, LiveRTSPGateway, MockFrameGateway


def test_ffprobe_strips_secrets():
    raw = {
        "streams": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_type": "video",
                "width": 1280,
                "height": 720,
                "filename": "rtsp://admin:pass@192.168.1.1/stream",
            }
        ],
        "format": {
            "filename": "rtsp://admin:pass@cam/secret",
            "format_name": "rtsp",
            "duration": "N/A",
        },
    }
    clean = sanitize_ffprobe(raw)
    blob = str(clean)
    assert "admin" not in blob
    assert "pass" not in blob
    assert "filename" not in blob
    assert clean["streams"][0]["width"] == 1280


def test_mock_clock_trust_server_receive():
    gw = MockFrameGateway()
    gw.start()
    fr = gw.get_latest_frame()
    assert fr is not None
    assert fr.clock_trust == ClockTrust.SERVER_RECEIVE
    assert fr.provenance.value == "MOCK"
    gw.stop()


def test_live_start_idempotent_and_invalidate():
    gw = LiveRTSPGateway("", camera_id="cam-x")
    gw.start()
    gw.start()  # must not spawn second worker when not configured / already started
    assert gw.health().decoder_status == DecoderStatus.NOT_CONFIGURED
    assert gw.health().extras.get("diagnostic_uri") == "REDACTED"
    assert gw.health().camera_lab_pass is False
    # measured size remains UNVERIFIED until a real frame
    assert gw.health().extras.get("size_source") == "UNVERIFIED"
    gw.invalidate()
    assert gw.get_latest_frame() is None
    gw.stop()


def test_measured_fps_from_recv_times():
    gw = LiveRTSPGateway("rtsp://192.168.1.9:554/x", camera_id="1")
    now = time.monotonic()
    for i in range(5):
        gw._recv_times.append(now + i * 0.1)
    fps = gw._measured_fps()
    assert 9.0 <= fps <= 11.0
    gw.stop()

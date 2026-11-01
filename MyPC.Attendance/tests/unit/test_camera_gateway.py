"""P02 camera gateway unit tests (no physical camera required)."""

from __future__ import annotations

from app.vision.camera.gateway import (
    DecoderStatus,
    LiveRTSPGateway,
    MockFrameGateway,
    StreamProvenance,
    sanitize_rtsp_for_log,
)


def test_sanitize_strips_password():
    uri = "rtsp://admin:s3cret@192.168.1.50:554/Streaming/Channels/101"
    clean = sanitize_rtsp_for_log(uri)
    assert "s3cret" not in clean
    assert "admin" not in clean
    assert "192.168.1.50" in clean


def test_mock_gateway_provenance():
    gw = MockFrameGateway()
    gw.start()
    fr = gw.get_latest_frame()
    assert fr is not None
    assert fr.provenance == StreamProvenance.MOCK
    h = gw.health()
    assert h.camera_lab_pass is False
    assert h.provenance == StreamProvenance.MOCK
    gw.stop()


def test_live_gateway_without_uri_not_configured():
    gw = LiveRTSPGateway("", camera_id="x")
    gw.start()
    assert gw.health().decoder_status == DecoderStatus.NOT_CONFIGURED
    assert gw.health().camera_lab_pass is False
    gw.stop()

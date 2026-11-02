"""RealCam reliability: corrupt-frame guard, stream fingerprint, lab next-step, CRUD dry-run."""

from __future__ import annotations

import numpy as np

from app.vision.camera.gateway import (
    DecoderStatus,
    LiveRTSPGateway,
    MockFrameGateway,
    frame_looks_corrupt,
    physical_stream_fingerprint,
)
from app.vision.camera.registry import CameraSourceRegistry, FrameAccessError
from app.vision.camera.gateway import StreamProvenance


def test_frame_corrupt_detects_black_slab():
    bad = np.zeros((480, 640, 3), dtype=np.uint8)
    assert frame_looks_corrupt(bad) is True
    good = np.full((480, 640, 3), 90, dtype=np.uint8)
    good[100:200, 100:200] = 200
    assert frame_looks_corrupt(good) is False


def test_physical_stream_fingerprint_strips_userinfo():
    a = physical_stream_fingerprint("rtsp://admin:secret@192.168.0.10:554/ch1/main")
    b = physical_stream_fingerprint("rtsp://192.168.0.10:554/ch1/main")
    assert a == b
    assert "secret" not in a
    assert a.endswith("/ch1/main")


def test_live_gateway_backoff_fields_default_tcp():
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="1", transport="tcp")
    assert gw._transport == "tcp"
    assert gw.stream_fingerprint.startswith("127.0.0.1:554")
    h = gw.health()
    assert h.camera_lab_pass is False
    assert "corrupt_frames" in (h.extras or {})


def test_registry_rejects_corrupt_for_biometric(tmp_path=None):
    reg = CameraSourceRegistry()
    gw = MockFrameGateway(camera_id="9")
    gw.start()
    bound = reg.bind(9, gw, provenance=StreamProvenance.MOCK, profile="MOCK")
    assert bound.camera_db_id == 9
    # MOCK cannot satisfy biometric LIVE requirement
    try:
        reg.get_frame(9, require_live=True, for_biometric=True)
        assert False, "expected FrameAccessError"
    except FrameAccessError as exc:
        assert exc.code in {"LIVE_REQUIRED", "BIOMETRIC_REQUIRES_LIVE", "MOCK_NOT_ALLOWED"}


def test_lab_next_step_distinguishes_pass_from_physical():
    from types import SimpleNamespace

    from app.api.cameras import _lab_run_out

    run = SimpleNamespace(
        run_id="r1",
        nonce="n",
        kind="CAMERA_LAB",
        camera_id=1,
        state="OWNER_REVIEWED",
        profile="MAIN",
        config_revision="abc",
        provenance="CAMERA_LIVE",
        decoded_w=2880,
        decoded_h=1620,
        fps_measured=20.0,
        frame_age_ms=40.0,
        owner_challenge="x",
        owner_reviewed_by="admin",
        expires_at=None,
        revoked=False,
        metrics_json='{"evidence_layers":{"LIVE_SOURCE_MEASURED":true,"PHYSICAL_CONNECTIVITY_REVIEWED":true},"review_kind":"SINGLE_OPERATOR_ACK"}',
        note_vi="ok",
    )
    out = _lab_run_out(run)
    assert out["camera_lab_pass"] is False
    assert out["face_validation_status"] == "N_A"
    assert out["next_action"] == "PROMOTE_PHYSICAL"
    assert "promote_physical" in out["allowed_actions"]
    assert out["checklist"]["face_pilot"] == "N_A"

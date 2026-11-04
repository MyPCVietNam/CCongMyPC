"""P02 integration: LIVE face-detect / mjpeg-ai / regions (synthetic frames; no attendance)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
from sqlalchemy import select

from app.models.entities import AttendanceEvent, CameraDevice, PilotApprovalRecord, RecognitionRegion
from app.vision.camera.gateway import (
    CameraFrame,
    ClockTrust,
    DecoderStatus,
    GatewayHealth,
    StreamProvenance,
)
from app.vision.faces.types import FaceBox, InferenceMode, PoseEstimate, QualityReport


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


class _StubGw:
    def __init__(self, camera_id: str, frame: CameraFrame):
        self.camera_id = camera_id
        self._frame = frame
        self.config_revision = frame.config_revision
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def get_latest_frame(self):
        return self._frame

    def get_latest_good_frame(self):
        return self._frame if self._frame.integrity_ok else None

    def health(self):
        return GatewayHealth(
            provenance=self._frame.provenance,
            decoder_status=self._frame.decoder_status,
            native_width=self._frame.width,
            native_height=self._frame.height,
            fps_estimate=20.0,
            operationally_ready=True,
        )

    def set_frame(self, fr: CameraFrame):
        self._frame = fr
        self.config_revision = fr.config_revision


def _mk_frame(
    *,
    camera_id: str = "1",
    frame_id: str = "frm-1",
    provenance=StreamProvenance.CAMERA_LIVE,
    status=DecoderStatus.OK,
    rev: str = "rev-p02",
    w: int = 320,
    h: int = 240,
    age_s: float = 0.0,
) -> CameraFrame:
    img = np.full((h, w, 3), 50, dtype=np.uint8)
    now = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return CameraFrame.from_bgr(
        img,
        frame_id=frame_id,
        camera_id=camera_id,
        capture_time_utc=now,
        receive_time_utc=now,
        provenance=provenance,
        decoder_status=status,
        config_revision=rev,
        clock_trust=ClockTrust.SERVER_RECEIVE,
        integrity_ok=True,
        receive_monotonic=__import__("time").monotonic() - age_s,
    )


def _bind_live(app, camera_id: int, frame: CameraFrame):
    from app.vision.camera.registry import CameraSourceRegistry

    reg = app.state.container.camera_registry or CameraSourceRegistry()
    app.state.container.camera_registry = reg
    gw = _StubGw(str(camera_id), frame)
    bound = reg.bind(camera_id, gw, provenance=frame.provenance, profile="MAIN")
    bound.config_revision = frame.config_revision
    return gw


class _Pipe:
    def __init__(self, faces, quality, mode=InferenceMode.REAL, ready=True):
        self._faces = faces
        self._q = quality
        self.inference_mode = mode
        self.detector = SimpleNamespace(info=SimpleNamespace(ready=ready, backend="opencv_dnn"))
        self.calls = 0

    def detect_and_quality(self, image, *, expected_slot=None, max_faces_ok=1):
        self.calls += 1
        return list(self._faces), self._q


def _q_ok(w=160):
    return QualityReport(
        ok=True,
        score=0.91,
        face_width_px=w,
        inter_eye_px=48.0,
        blur_score=1.0,
        laplacian_var=120.0,
        pose=PoseEstimate(0, 0, 0, "FACE_FRONT", 0.7),
        hard_fail=False,
        reasons_vi=[],
        breakdown={},
        metadata={},
    )


def _seed_camera(app, *, mock=False, rev="rev-p02"):
    with app.state.container.session_factory() as db:
        cam = CameraDevice(
            name="P02 Synthetic",
            host="192.168.0.211",
            mock_mode=mock,
            enabled=True,
            archived=False,
            created_at=datetime.now(timezone.utc),
            config_revision=rev,
            username_hint="admin",
            secret_ref="camera-p02.bin",
        )
        db.add(cam)
        db.flush()
        cid = cam.id
        db.add(
            RecognitionRegion(
                camera_id=cid,
                name="arrival",
                norm_rect_json='{"x":0.2,"y":0.1,"w":0.5,"h":0.4}',
                calibration_version=3,
            )
        )
        db.commit()
    return cid


def test_regions_get_and_put_preserves_camera_lab(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    # Seed a fake signed lab approval row — ROI must not revoke it
    with app.state.container.session_factory() as db:
        now = datetime.now(timezone.utc)
        db.add(
            PilotApprovalRecord(
                approval_id="ap-lab-p02",
                kind="CAMERA_LAB",
                camera_id=cid,
                payload_json="{}",
                signature="00",
                issued_at=now,
                expires_at=now + timedelta(days=1),
                revoked=False,
                note_vi="fixture",
            )
        )
        db.commit()

    g = client.get(f"/api/v1/cameras/{cid}/regions")
    assert g.status_code == 200
    body = g.json()
    assert body["has_saved_roi"] is True
    assert body["roi"]["x"] == 0.2
    assert body["calibration_version"] == 3

    r = client.put(
        f"/api/v1/cameras/{cid}/regions",
        headers=hdr,
        json={"name": "arrival", "x": 0.25, "y": 0.1, "w": 0.4, "h": 0.3},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["camera_lab_revoked"] is False
    assert out["trust_gate"]["revokes_camera_lab_hmac"] is False
    assert out["trust_gate"]["rotates_config_revision"] is False
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, cid)
        assert cam.config_revision == "rev-p02"
        ap = db.scalar(
            select(PilotApprovalRecord).where(PilotApprovalRecord.approval_id == "ap-lab-p02")
        )
        assert ap is not None and ap.revoked is False


def test_face_detect_auth_and_mock_reject(app_client):
    client, app = app_client
    cid = _seed_camera(app, mock=True)
    # unauthenticated
    r = client.get(f"/api/v1/cameras/{cid}/live/face-detect")
    assert r.status_code in {401, 403}
    hdr = _login(client)
    # mock camera
    r2 = client.get(f"/api/v1/cameras/{cid}/live/face-detect", headers=hdr)
    assert r2.status_code == 422
    assert r2.json()["detail"]["code"] == "REJECTED_MOCK"


def test_face_detect_ok_and_no_attendance(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    fr = _mk_frame(camera_id=str(cid), frame_id="live-ok-1", rev="rev-p02")
    _bind_live(app, cid, fr)
    # Center (~115,95) stays inside seeded ROI x=0.2..0.7, y=0.1..0.5 on 320x240
    app.state.container.face_pipeline = _Pipe([FaceBox(30, 40, 170, 110, 0.93)], _q_ok(170))

    before = 0
    with app.state.container.session_factory() as db:
        before = db.scalar(select(AttendanceEvent)) is not None

    r = client.get(f"/api/v1/cameras/{cid}/live/face-detect?max_ai_fps=2", headers=hdr)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["frame_id"] == "live-ok-1"
    assert data["status"] == "OK"
    assert data["face_count"] == 1
    assert data["faces"][0]["w_px"] == 170
    assert data["identity_exposed"] is False
    assert data["attendance_written"] is False
    assert data["phase"] == "DETECTION_QUALITY_ONLY"
    assert data["live_stability_pass"] is False

    with app.state.container.session_factory() as db:
        n = db.scalar(select(AttendanceEvent))
        assert n is None or before


def test_face_detect_stale_and_switch_race(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    stale = _mk_frame(camera_id=str(cid), frame_id="old", status=DecoderStatus.STALE, age_s=0.0)
    gw = _bind_live(app, cid, stale)
    app.state.container.face_pipeline = _Pipe([FaceBox(10, 10, 160, 160, 0.9)], _q_ok())
    # STALE may be rejected by registry allow_stale=False OR by service
    r = client.get(f"/api/v1/cameras/{cid}/live/face-detect", headers=hdr)
    assert r.status_code in {200, 503}
    if r.status_code == 200:
        assert r.json()["status"] in {"STALE_FRAME", "NOT_READY", "NO_FACE", "OK"}
    else:
        assert r.json()["detail"]["code"]

    # camera switch: rebind new frame id
    fresh = _mk_frame(camera_id=str(cid), frame_id="fresh-2", rev="rev-p02")
    gw.set_frame(fresh)
    app.state.container.face_detect_preview.clear_camera(cid)
    r2 = client.get(f"/api/v1/cameras/{cid}/live/face-detect", headers=hdr)
    assert r2.status_code == 200
    assert r2.json()["frame_id"] == "fresh-2"


def test_mjpeg_ai_stream_headers(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    fr = _mk_frame(camera_id=str(cid), frame_id="ai-1")
    _bind_live(app, cid, fr)
    app.state.container.face_pipeline = _Pipe([FaceBox(20, 20, 150, 160, 0.9)], _q_ok(150))
    with client.stream("GET", f"/api/v1/cameras/{cid}/preview/mjpeg-ai?max_ai_fps=1", headers=hdr) as resp:
        assert resp.status_code == 200
        assert "LIVE_MJPEG_AI" in resp.headers.get("x-view-mode", resp.headers.get("X-View-Mode", ""))
        assert resp.headers.get("x-phase", resp.headers.get("X-Phase", "")) == "DETECTION_QUALITY_ONLY"
        # read a small chunk then close (generator ends on client disconnect)
        chunk = next(resp.iter_bytes())
        assert b"--frame" in chunk or b"\xff\xd8" in chunk or len(chunk) > 0


def test_not_ready_without_real_model(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    fr = _mk_frame(camera_id=str(cid), frame_id="nr-1")
    _bind_live(app, cid, fr)
    app.state.container.face_pipeline = _Pipe(
        [FaceBox(1, 1, 200, 200, 0.9)],
        _q_ok(),
        mode=InferenceMode.SYNTHETIC_FIXTURE,
        ready=True,
    )
    r = client.get(f"/api/v1/cameras/{cid}/live/face-detect", headers=hdr)
    assert r.status_code == 200
    assert r.json()["status"] == "NOT_READY"
    assert r.json()["faces"] == []


def test_rate_limit_cache_reduces_inference(app_client):
    client, app = app_client
    hdr = _login(client)
    cid = _seed_camera(app)
    fr = _mk_frame(camera_id=str(cid), frame_id="cache-1")
    _bind_live(app, cid, fr)
    pipe = _Pipe([FaceBox(20, 20, 160, 170, 0.9)], _q_ok())
    app.state.container.face_pipeline = pipe
    app.state.container.face_detect_preview.clear_camera(cid)
    a = client.get(f"/api/v1/cameras/{cid}/live/face-detect?max_ai_fps=1", headers=hdr)
    b = client.get(f"/api/v1/cameras/{cid}/live/face-detect?max_ai_fps=1", headers=hdr)
    assert a.status_code == 200 and b.status_code == 200
    assert pipe.calls == 1
    assert b.json()["cache_hit"] is True

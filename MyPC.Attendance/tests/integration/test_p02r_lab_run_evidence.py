"""P02R: lab-run FSM — PHYSICAL_VERIFIED needs LIVE measure + owner review + cases."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.vision.camera.gateway import (
    CameraFrame,
    ClockTrust,
    DecoderStatus,
    GatewayHealth,
    StreamProvenance,
)


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf_token"]}


class _LiveStub:
    def __init__(self, camera_id: str, w=160, h=120, provenance=StreamProvenance.CAMERA_LIVE):
        self.camera_id = camera_id
        self.config_revision = "stub"
        self._running = False
        self.w, self.h = w, h
        self.provenance = provenance
        self._n = 0

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def get_latest_frame(self):
        if not self._running:
            return None
        now = datetime.now(timezone.utc)
        self._n += 1
        img = np.full((self.h, self.w, 3), 90, dtype=np.uint8)
        return CameraFrame.from_bgr(
            img,
            frame_id=f"f-{self._n}",
            camera_id=self.camera_id,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=self.provenance,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
        )

    def health(self):
        return GatewayHealth(
            provenance=self.provenance,
            decoder_status=DecoderStatus.OK,
            native_width=self.w,
            native_height=self.h,
            fps_estimate=8.0,
            detail_vi="stub",
            camera_lab_pass=False,
            operationally_ready=False,
        )


def _bind_live(app, cam_id: int, stub: _LiveStub | None = None):
    stub = stub or _LiveStub(str(cam_id))
    stub.start()
    bound = app.state.container.camera_registry.bind(
        cam_id, stub, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN"
    )
    stub.config_revision = bound.config_revision
    return stub, bound


def test_ev01_client_label_counts_rejected_for_physical(app_client):
    """EV01: labeled_known/unknown without server cases cannot create PHYSICAL."""
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "EV01", "host": "192.168.1.80", "mock_mode": True, "enabled": True},
    ).json()
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/evidence/record",
        headers=headers,
        json={
            "kind": "FACE_PILOT",
            "evidence_class": "PHYSICAL_VERIFIED",
            "labeled_known": 20,
            "labeled_unknown": 20,
            "observed_width": 160,
            "observed_height": 120,
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NEED_LAB_RUN_PROMOTE"


def test_ev05_mock_measure_rejected(app_client):
    """EV05: MOCK provenance cannot LIVE_MEASURE for physical path."""
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "EV05", "mock_mode": True, "enabled": True},
    ).json()
    # Preview binds MOCK
    assert client.get(f"/api/v1/cameras/{cam['id']}/preview").status_code == 200
    start = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs",
        headers=headers,
        json={"kind": "CAMERA_LAB"},
    )
    assert start.status_code == 200, start.text
    run_id = start.json()["run_id"]
    meas = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/measure",
        headers=headers,
        json={"samples": 3},
    )
    assert meas.status_code == 422
    assert meas.json()["detail"]["code"] in {
        "PROVENANCE_NOT_LIVE",
        "LIVE_NOT_BOUND",
        "FRAME_ACCESS",
        "NOT_LIVE",
        "PROVENANCE_REQUIRED",
    }


def test_ev11_promote_without_owner_review_rejected(app_client):
    """EV11: cannot PHYSICAL_VERIFIED without OWNER_REVIEWED."""
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "EV11", "host": "192.168.1.81", "mock_mode": False, "enabled": True},
    ).json()
    stub, _ = _bind_live(app, cam["id"])
    start = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs",
        headers=headers,
        json={"kind": "CAMERA_LAB"},
    )
    assert start.status_code == 200
    run_id = start.json()["run_id"]
    challenge = start.json()["owner_challenge"]
    meas = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/measure",
        headers=headers,
        json={"samples": 3},
    )
    assert meas.status_code == 200, meas.text
    assert meas.json()["state"] == "LIVE_MEASURED"
    assert meas.json()["decoded_w"] == 160
    # Promote without owner review
    promo = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/promote-physical",
        headers=headers,
        json={},
    )
    assert promo.status_code == 422
    assert promo.json()["detail"]["code"] == "NEED_OWNER_REVIEW"
    # Wrong challenge
    bad = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/owner-review",
        headers=headers,
        json={"challenge": "wrong"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "CHALLENGE_INVALID"
    ok = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/owner-review",
        headers=headers,
        json={"challenge": challenge},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "OWNER_REVIEWED"
    promo2 = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/promote-physical",
        headers=headers,
        json={},
    )
    assert promo2.status_code == 200, promo2.text
    assert promo2.json()["evidence_class"] == "PHYSICAL_VERIFIED"
    assert promo2.json()["lab_run_id"] == run_id
    assert promo2.json()["camera_lab_pass"] is False
    stub.stop()


def test_ev02_disconnected_cannot_measure(app_client):
    """EV02: previously LIVE but stopped — measure fail-closed."""
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "EV02", "host": "192.168.1.82", "mock_mode": False, "enabled": True},
    ).json()
    stub, _ = _bind_live(app, cam["id"])
    start = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs",
        headers=headers,
        json={"kind": "CAMERA_LAB"},
    ).json()
    stub.stop()
    meas = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{start['run_id']}/measure",
        headers=headers,
        json={"samples": 3},
    )
    assert meas.status_code == 422


def test_face_pilot_needs_server_cases_before_owner_review(app_client):
    """FACE_PILOT owner review requires ≥1 KNOWN + ≥1 UNKNOWN server cases."""
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "FP", "host": "192.168.1.83", "mock_mode": False, "enabled": True},
    ).json()
    stub, _ = _bind_live(app, cam["id"])
    start = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs",
        headers=headers,
        json={"kind": "FACE_PILOT"},
    ).json()
    run_id = start["run_id"]
    challenge = start["owner_challenge"]
    assert (
        client.post(
            f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/measure",
            headers=headers,
            json={"samples": 3},
        ).status_code
        == 200
    )
    # Owner review without cases
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/lab-runs/{run_id}/owner-review",
        headers=headers,
        json={"challenge": challenge},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "FACE_CASES_INSUFFICIENT"
    stub.stop()


def test_sec_csrf_lab_run_rejected(app_client):
    client, _ = app_client
    cam = client.post(
        "/api/v1/cameras",
        headers=_login(client),
        json={"name": "SEC", "mock_mode": True},
    ).json()
    r = client.post(f"/api/v1/cameras/{cam['id']}/lab-runs", json={"kind": "CAMERA_LAB"})
    assert r.status_code in {401, 403}


def test_env10_mock_cannot_unlock_camera_lab(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "ENV10", "mock_mode": True, "enabled": True},
    ).json()
    h = client.get("/api/v1/cameras/gateway/health", params={"camera_id": cam["id"]})
    assert h.status_code == 200
    assert h.json().get("camera_lab_pass") is False
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["gates"]["CAMERA_LAB_PASS"] is False
    assert body["gates"]["FACE_PILOT_PASS"] is False

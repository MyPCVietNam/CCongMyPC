"""PR7 evidence gates — client AB untrusted; CAMERA_LAB needs PHYSICAL evidence."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select

from app.models.biometric import EnrollmentSession
from app.models.entities import CameraDevice, CameraLabRun
from app.services.evidence_store import EVIDENCE_PHYSICAL, create_evidence
from app.services.pilot_approval import issue_approval
from app.services.server_pins import derive_live_pins
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
    def __init__(self, camera_id: str, w=160, h=120):
        self.camera_id = camera_id
        self.config_revision = "stub"
        self._running = False
        self.w, self.h = w, h
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
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
            integrity_ok=True,
        )

    def get_latest_good_frame(self):
        fr = self.get_latest_frame()
        return fr if fr is not None and fr.integrity_ok else None

    def health(self):
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK if self._running else DecoderStatus.STOPPED,
            native_width=self.w,
            native_height=self.h,
            fps_estimate=8.0,
            detail_vi="stub",
            camera_lab_pass=False,
            operationally_ready=bool(self._running),
        )


def test_client_ab_is_untrusted_and_not_promotable(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "ABU", "host": "192.168.1.70", "mock_mode": True, "enabled": True},
    ).json()
    pairs = [
        {
            "case_id": "1",
            "frame_id": "a",
            "source": "LIVE",
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
    ]
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/evaluation/run",
        headers=headers,
        json={"pairs": pairs, "claimed_source": "LIVE"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence_class"] == "UNTRUSTED_IMPORT"
    assert body["can_auto_enable_enhancement"] is False
    assert body["approval_status"] == "REJECTED"

    # AUTO_VALIDATED must reject this run
    av = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/approvals",
        headers=headers,
        json={"kind": "AUTO_VALIDATED", "ab_run_id": body["run_id"]},
    )
    assert av.status_code == 422
    assert av.json()["detail"]["code"] in {
        "AB_NOT_PHYSICAL",
        "AB_CAN_AUTO_ENABLE_FALSE",
        "AB_NOT_APPROVED",
        "AB_HAS_SEVERE_BLOCKER",
        "AB_RUN_INSUFFICIENT",
    }


def test_camera_lab_rejected_without_physical_evidence(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Lab", "host": "192.168.1.71", "mock_mode": True, "enabled": True},
    ).json()
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "admin_confirm": True},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "CHECKBOX_REJECTED"
    r2 = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB"},
    )
    assert r2.status_code == 422
    assert r2.json()["detail"]["code"] in {
        "EVIDENCE_ID_REQUIRED",
        "EVIDENCE_NOT_FOUND",
    }


def test_physical_evidence_rejected_on_mock(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "MockLab", "mock_mode": True, "enabled": True},
    ).json()
    assert client.get(f"/api/v1/cameras/{cam['id']}/preview").status_code == 200
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/evidence/record",
        headers=headers,
        json={
            "kind": "CAMERA_LAB",
            "evidence_class": "PHYSICAL_VERIFIED",
            "observed_width": 640,
            "observed_height": 360,
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] in {
        "PHYSICAL_REQUIRES_LIVE_DECODE",
        "NEED_LAB_RUN_PROMOTE",
    }


def test_gateway_health_separates_settings_flag(app_client):
    client, app = app_client
    headers = _login(client)
    app.state.container.settings.camera_lab_pass = True
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "H", "mock_mode": True},
    ).json()
    h = client.get("/api/v1/cameras/gateway/health", params={"camera_id": cam["id"]})
    assert h.status_code == 200
    body = h.json()
    assert body.get("settings_flag_camera_lab") is True
    assert body.get("camera_lab_pass") is False
    assert body.get("signed_camera_lab") is False


def test_config_revision_invalidation_persists(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Persist", "host": "192.168.1.72", "mock_mode": False, "enabled": True},
    ).json()
    stub = _LiveStub(str(cam["id"]))
    stub.start()
    bound = app.state.container.camera_registry.bind(
        cam["id"], stub, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN"
    )
    stub.config_revision = bound.config_revision
    pins, _ = None, None
    factory = app.state.container.session_factory
    with factory() as db:
        pins, _ = derive_live_pins(
            db, pipeline=app.state.container.face_pipeline, store=app.state.container.template_store
        )
        cam_row = db.get(CameraDevice, cam["id"])
        assert cam_row is not None
        cam_row.config_revision = bound.config_revision
        db.add(
            CameraLabRun(
                run_id="test-lab-run-pr7-inv",
                nonce="nonce-pr7-inv",
                kind="CAMERA_LAB",
                camera_id=cam["id"],
                state="PHYSICAL_VERIFIED",
                revoked=False,
                config_revision=bound.config_revision,
                provenance="CAMERA_LIVE",
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                decoded_w=160,
                decoded_h=120,
                started_at=datetime.now(timezone.utc),
                owner_reviewed_by="admin",
                owner_reviewed_at=datetime.now(timezone.utc),
            )
        )
        ev = create_evidence(
            db,
            kind="CAMERA_LAB",
            evidence_class=EVIDENCE_PHYSICAL,
            camera_id=cam["id"],
            operator="admin",
            pins=pins,
            config_revision=bound.config_revision,
            provenance="CAMERA_LIVE",
            decoded_w=160,
            decoded_h=120,
            lab_run_id="test-lab-run-pr7-inv",
        )
        issue_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cam["id"],
            issued_by="admin",
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
            evidence_id=ev.evidence_id,
        )
        db.commit()

    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "E-PR7-INV", "full_name": "Invalidation"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "A",
            "authorization_ack_vi": "Tôi xác nhận đồng ý thu thập khuôn mặt.",
            "source": "REAL_CAMERA",
            "camera_id": cam["id"],
        },
    )
    assert start.status_code == 200, start.text
    sid = start.json()["session_id"]
    # Change config revision on registry (bind stops gateway — restart stub)
    bound2 = app.state.container.camera_registry.bind(
        cam["id"], stub, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN"
    )
    stub.start()
    stub.config_revision = bound2.config_revision
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CONFIG_REVISION_CHANGED"
    # Fresh DB session must see FAILED
    with factory() as db2:
        row = db2.scalar(select(EnrollmentSession).where(EnrollmentSession.public_id == sid))
        assert row is not None
        assert row.status == "FAILED"
    stub.stop()

"""PR6 follow-up integration: enrollment camera bind, evidence approvals, gallery A/B."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.models.entities import AbEvaluationRun
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
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


class _LiveStub:
    """Test-only CAMERA_LIVE frame source — not physical evidence."""

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.config_revision = "stub-rev"
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def get_latest_frame(self):
        if not self._running:
            return None
        now = datetime.now(timezone.utc)
        img = np.full((120, 160, 3), 90, dtype=np.uint8)
        return CameraFrame.from_bgr(
            img,
            frame_id="stub-f1",
            camera_id=self.camera_id,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
        )

    def health(self):
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK,
            native_width=160,
            native_height=120,
            detail_vi="STUB LIVE — không phải camera vật lý",
            camera_lab_pass=False,
            operationally_ready=False,
        )


def _ensure_employee(client, headers, code: str = "E-PR6"):
    r = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": code, "full_name": "Nhân Viên PR6"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _pins(app):
    factory = app.state.container.session_factory
    with factory() as db:
        pins, snap = derive_live_pins(
            db,
            pipeline=app.state.container.face_pipeline,
            store=app.state.container.template_store,
        )
        return pins, snap


def test_real_camera_start_requires_camera_id(app_client):
    client, _ = app_client
    headers = _login(client)
    emp = _ensure_employee(client, headers)
    r = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "AUTH-1",
            "authorization_ack_vi": "Tôi xác nhận đồng ý thu thập khuôn mặt.",
            "source": "REAL_CAMERA",
        },
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "CAMERA_ID_REQUIRED"


def test_real_camera_rejected_without_signed_lab_even_with_staging(app_client):
    client, app = app_client
    # Staging flag alone must not bypass
    app.state.container.settings.allow_live_enrollment_staging = True
    app.state.container.settings.camera_lab_pass = True
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "CamA", "host": "192.168.1.40", "mock_mode": False, "enabled": True},
    ).json()
    emp = _ensure_employee(client, headers, code="E-PR6-STAGING")
    r = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "AUTH-2",
            "authorization_ack_vi": "Tôi xác nhận đồng ý thu thập khuôn mặt.",
            "source": "REAL_CAMERA",
            "camera_id": cam["id"],
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "CAMERA_LAB_BLOCKED"


def test_demo_frame_rejects_live_camera_id(app_client):
    client, _ = app_client
    headers = _login(client)
    emp = _ensure_employee(client, headers, code="E-PR6-DEMO")
    start = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "AUTH-3",
            "authorization_ack_vi": "Tôi xác nhận đồng ý thu thập khuôn mặt.",
            "source": "DEMO",
        },
    )
    assert start.status_code == 200, start.text
    sid = start.json()["session_id"]
    r = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={"camera_id": 1, "image_base64": None},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CROSS_SOURCE_REJECTED"


def test_real_camera_bound_rejects_cross_camera_and_client_image(app_client):
    client, app = app_client
    headers = _login(client)
    cam_a = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "A", "host": "192.168.1.41", "mock_mode": False, "enabled": True},
    ).json()
    cam_b = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "B", "host": "192.168.1.42", "mock_mode": False, "enabled": True},
    ).json()

    pins, _ = _pins(app)
    stub = _LiveStub(str(cam_a["id"]))
    stub.start()
    bound = app.state.container.camera_registry.bind(
        cam_a["id"], stub, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN"
    )
    stub.config_revision = bound.config_revision

    factory = app.state.container.session_factory
    with factory() as db:
        from app.services.evidence_store import EVIDENCE_PHYSICAL, create_evidence

        ev = create_evidence(
            db,
            kind="CAMERA_LAB",
            evidence_class=EVIDENCE_PHYSICAL,
            camera_id=cam_a["id"],
            operator="admin",
            pins=pins,
            config_revision=bound.config_revision,
            provenance="CAMERA_LIVE",
            decoded_w=160,
            decoded_h=120,
            fps_measured=5.0,
            lab_run_id="test-lab-run-pr6-bind",
        )
        issue_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cam_a["id"],
            issued_by="admin",
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
            evidence_id=ev.evidence_id,
        )
        db.commit()

    emp = _ensure_employee(client, headers, code="E-PR6-BIND")
    start = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "AUTH-4",
            "authorization_ack_vi": "Tôi xác nhận đồng ý thu thập khuôn mặt.",
            "source": "REAL_CAMERA",
            "camera_id": cam_a["id"],
        },
    )
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["camera_id"] == cam_a["id"]
    assert body["camera_lab_approval_id"]
    sid = body["session_id"]

    # Cross-camera frame rejected
    bad = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={"camera_id": cam_b["id"]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "CAMERA_REBIND_REJECTED"

    # Client image rejected on LIVE session
    import base64
    import cv2

    png = cv2.imencode(".png", np.zeros((32, 32, 3), dtype=np.uint8))[1].tobytes()
    bad2 = client.post(
        f"/api/v1/employees/{emp}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={"image_base64": base64.b64encode(png).decode("ascii")},
    )
    assert bad2.status_code == 422
    assert bad2.json()["detail"]["code"] == "CLIENT_IMAGE_NOT_LIVE"
    stub.stop()


def test_auto_validated_rejects_blank_ab_and_fake_pins(app_client):
    client, app = app_client
    headers = _login(client)
    # Ensure PILOT_APPROVE (SYSTEM_ADMIN has it)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Apr", "host": "192.168.1.55", "mock_mode": True, "enabled": True},
    ).json()
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/approvals",
        headers=headers,
        json={"kind": "AUTO_VALIDATED", "ab_run_id": "", "model_hash_pin": "fake"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    # Either client pin mismatch or AB required
    if isinstance(detail, dict):
        assert detail["code"] in {"CLIENT_PIN_MISMATCH", "AB_RUN_REQUIRED"}
    else:
        assert "ab_run" in str(detail).lower() or "pin" in str(detail).lower()


def test_auto_validated_requires_lab_and_pilot_evidence(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Apr2", "host": "192.168.1.56", "mock_mode": True, "enabled": True},
    ).json()
    factory = app.state.container.session_factory
    with factory() as db:
        db.add(
            AbEvaluationRun(
                camera_id=cam["id"],
                run_id="ab-live-1",
                source_mix="LIVE",
                sample_count=12,
                metrics_json="{}",
                blockers_json="[]",
                can_auto_enable=False,
                approval_status="PENDING",
                created_at=datetime.now(timezone.utc),
                note_vi="test",
            )
        )
        db.commit()
    r = client.post(
        f"/api/v1/cameras/{cam['id']}/quality/approvals",
        headers=headers,
        json={"kind": "AUTO_VALIDATED", "ab_run_id": "ab-live-1"},
    )
    assert r.status_code == 422
    # PR7: untrusted/non-physical AB is rejected before pilot check
    assert r.json()["detail"]["code"] in {
        "PILOT_EVIDENCE_MISSING",
        "AB_NOT_PHYSICAL",
        "AB_NOT_APPROVED",
        "AB_CAN_AUTO_ENABLE_FALSE",
        "AB_HAS_SEVERE_BLOCKER",
    }


def test_quality_settings_stay_test_only_without_approval(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Q", "mock_mode": True},
    ).json()
    r = client.put(
        f"/api/v1/cameras/{cam['id']}/quality/settings",
        headers=headers,
        json={"requested_mode": "AUTO_VALIDATED", "model_hash_pin": "x"},
    )
    assert r.status_code == 200
    assert r.json()["effective_mode"] == "AUTO_TEST_ONLY"


def test_analyze_once_honest_gallery_status(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "AB", "mock_mode": True, "enabled": True},
    ).json()
    # Preview binds MOCK gateway
    assert client.get(f"/api/v1/cameras/{cam['id']}/preview").status_code == 200
    r = client.post(f"/api/v1/cameras/{cam['id']}/quality/analyze-once", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gallery_status"] == "BLOCKED_GALLERY"
    assert body["gallery_count"] == 0
    assert body["paired"]["status"] in {"BLOCKED_GALLERY", "DEMO_SYNTHETIC", "BLOCKED_MODEL"}
    assert body["paired"].get("can_auto_enable_enhancement") is False
    assert body["effective_mode"] == "AUTO_TEST_ONLY"


def test_rtsp_configure_rejects_hostname(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "RTSP", "host": "192.168.1.60", "mock_mode": False, "enabled": True},
    ).json()
    r = client.post(
        "/api/v1/cameras/gateway/live/configure",
        headers=headers,
        json={
            "camera_id": cam["id"],
            "rtsp_uri": "rtsp://cam-office.local:554/Streaming/Channels/101",
            "profile": "MAIN",
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "RTSP_POLICY"

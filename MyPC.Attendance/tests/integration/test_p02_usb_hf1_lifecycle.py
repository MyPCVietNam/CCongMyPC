"""P02-USB-HF1: same-device revision preserve, device switch revoke, no EZVIZ transfer."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from sqlalchemy import select

from app.core.utc_time import utc_now
from app.models.entities import (
    CameraDevice,
    CameraLabRun,
    CameraLiveBinding,
    PilotApprovalRecord,
    PilotEvidenceRecord,
)
from app.services.pilot_approval import issue_approval, verify_active_approval
from app.vision.camera.usb_device import (
    UsbDeviceInfo,
    fingerprint_stable_id,
    set_usb_enumerator_for_tests,
)

PINS = {
    "model_hash_pin": "synthetic-model-pin",
    "gallery_revision_pin": "synthetic-gallery-revision",
    "threshold_id_pin": "synthetic-threshold-pin",
}
KEY = "synthetic-not-for-production-approval-key-usb-hf1"


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf_token"]}


class _FakeCap:
    def __init__(self):
        self.opened = True
        self.frame = np.random.default_rng(11).integers(20, 180, (480, 640, 3), dtype=np.uint8)

    def isOpened(self):
        return self.opened

    def set(self, *a):
        return True

    def get(self, p):
        return {3: 640, 4: 480, 5: 25, 6: 0}.get(p, 0)

    def read(self):
        return True, self.frame.copy()

    def release(self):
        self.opened = False


def _enum(devices: list[UsbDeviceInfo]):
    class E:
        def list_devices(self):
            return list(devices)

    set_usb_enumerator_for_tests(E())


def test_index_reorder_same_stable_preserves_revision(app_client):
    client, app = app_client
    headers = _login(client)
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-REORDER")
    _enum(
        [
            UsbDeviceInfo(
                stable_id=sid,
                friendly_name="UGREEN Camera 4K",
                index_hint=2,
                ambiguous=False,
                mapping_verified=True,
                capture_mapping_verified=True,
                device_path_fingerprint="synthetic-dpath-fp",
            )
        ]
    )
    app.state.container.usb_open_capture = lambda i, b: _FakeCap()
    try:
        cam = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "U", "source_type": "USB_UVC", "mock_mode": False, "credential_action": "keep"},
        ).json()
        cid = cam["id"]
        r1 = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cid, "stable_id": sid},
        )
        assert r1.status_code == 200, r1.text
        rev1 = r1.json()["config_revision"]
        # Simulate unplug/replug: same stable_id, different index_hint
        _enum(
            [
                UsbDeviceInfo(
                    stable_id=sid,
                    friendly_name="UGREEN Camera 4K",
                    index_hint=0,
                    ambiguous=False,
                    mapping_verified=True,
                    capture_mapping_verified=True,
                    device_path_fingerprint="synthetic-dpath-fp",
                )
            ]
        )
        r2 = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cid, "stable_id": sid},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["config_revision"] == rev1
        assert r2.json().get("revision_preserved") is True
    finally:
        set_usb_enumerator_for_tests(None)
        app.state.container.usb_open_capture = None


def test_different_usb_device_rotates_and_revokes(app_client):
    client, app = app_client
    headers = _login(client)
    sid_a = fingerprint_stable_id("USB\\VID_AAAA&PID_0001\\A")
    sid_b = fingerprint_stable_id("USB\\VID_BBBB&PID_0002\\B")
    _enum(
        [
            UsbDeviceInfo(
                stable_id=sid_a,
                friendly_name="Cam A",
                index_hint=1,
                ambiguous=False,
                mapping_verified=True,
                capture_mapping_verified=True,
                device_path_fingerprint="synthetic-dpath-fp",
            ),
            UsbDeviceInfo(
                stable_id=sid_b,
                friendly_name="Cam B",
                index_hint=2,
                ambiguous=False,
                mapping_verified=True,
                capture_mapping_verified=True,
                device_path_fingerprint="synthetic-dpath-fp",
            ),
        ]
    )
    app.state.container.usb_open_capture = lambda i, b: _FakeCap()
    try:
        cam = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "switch", "source_type": "USB_UVC", "mock_mode": False, "credential_action": "keep"},
        ).json()
        cid = cam["id"]
        r1 = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cid, "stable_id": sid_a},
        )
        assert r1.status_code == 200
        rev1 = r1.json()["config_revision"]
        # Seed a signed CAMERA_LAB against rev1
        factory = app.state.container.session_factory
        with factory() as db:
            now = utc_now()
            db.add(
                CameraLabRun(
                    run_id="run-usb-a",
                    nonce="nonce-usb-a",
                    kind="CAMERA_LAB",
                    camera_id=cid,
                    state="PHYSICAL_VERIFIED",
                    revoked=False,
                    config_revision=rev1,
                    provenance="CAMERA_LIVE",
                    decoded_w=1920,
                    decoded_h=1080,
                    fps_measured=20.0,
                    owner_reviewed_by="owner",
                    owner_reviewed_at=now,
                    started_at=now,
                    expires_at=now + timedelta(hours=7),
                    **PINS,
                )
            )
            db.add(
                PilotEvidenceRecord(
                    evidence_id="ev-usb-a",
                    kind="CAMERA_LAB",
                    evidence_class="PHYSICAL_VERIFIED",
                    camera_id=cid,
                    lab_run_id="run-usb-a",
                    config_revision=rev1,
                    provenance="CAMERA_LIVE",
                    decoded_w=1920,
                    decoded_h=1080,
                    fps_measured=20.0,
                    operator="owner",
                    created_at=now,
                    payload_json="{}",
                    **PINS,
                )
            )
            db.flush()
            issue_approval(
                db,
                secret_key=KEY,
                kind="CAMERA_LAB",
                camera_id=cid,
                issued_by="owner",
                evidence_id="ev-usb-a",
                **PINS,
            )
            db.commit()
            assert verify_active_approval(
                db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cid, **PINS
            )

        r2 = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cid, "stable_id": sid_b},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["config_revision"] != rev1
        assert (r2.json().get("trust_lifecycle") or {}).get("material") is True
        with factory() as db:
            v = verify_active_approval(
                db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cid, **PINS
            )
            assert v is None or not v.valid
            # Historical evidence retained
            ev = db.scalar(
                select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == "ev-usb-a")
            )
            assert ev is not None
            appr = db.scalar(select(PilotApprovalRecord).limit(1))
            assert appr is not None and bool(appr.revoked)
    finally:
        set_usb_enumerator_for_tests(None)
        app.state.container.usb_open_capture = None


def test_allow_ambiguous_rejected_for_trusted_live(app_client):
    client, app = app_client
    headers = _login(client)
    sid = fingerprint_stable_id("opencv-index:3")
    _enum(
        [
            UsbDeviceInfo(
                stable_id=sid,
                friendly_name="OpenCV camera index 3 (tạm thời)",
                index_hint=3,
                ambiguous=True,
            )
        ]
    )
    app.state.container.usb_open_capture = lambda i, b: _FakeCap()
    try:
        cam = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "amb", "source_type": "USB_UVC", "mock_mode": False, "credential_action": "keep"},
        ).json()
        r = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cam["id"], "stable_id": sid, "allow_ambiguous": True},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "USB_AMBIGUOUS_NOT_TRUSTED_LIVE"
    finally:
        set_usb_enumerator_for_tests(None)
        app.state.container.usb_open_capture = None


def test_duplicate_lease_conflict(app_client):
    client, app = app_client
    headers = _login(client)
    sid = fingerprint_stable_id("USB\\VID_DUP&PID_0001\\X")
    _enum(
        [
            UsbDeviceInfo(
                stable_id=sid,
                friendly_name="UGREEN Camera 4K",
                index_hint=1,
                ambiguous=False,
                mapping_verified=True,
                capture_mapping_verified=True,
                device_path_fingerprint="synthetic-dpath-fp",
            )
        ]
    )
    app.state.container.usb_open_capture = lambda i, b: _FakeCap()
    try:
        a = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "A", "source_type": "USB_UVC", "mock_mode": False, "credential_action": "keep"},
        ).json()["id"]
        b = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "B", "source_type": "USB_UVC", "mock_mode": False, "credential_action": "keep"},
        ).json()["id"]
        assert (
            client.post(
                "/api/v1/cameras/gateway/live/configure-usb",
                headers=headers,
                json={"camera_id": a, "stable_id": sid},
            ).status_code
            == 200
        )
        conflict = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": b, "stable_id": sid},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "USB_DEVICE_IN_USE"
    finally:
        set_usb_enumerator_for_tests(None)
        app.state.container.usb_open_capture = None

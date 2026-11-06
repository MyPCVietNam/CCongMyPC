"""P02-USB API: enumerate / diagnose / configure-usb with injectable fake capture."""

from __future__ import annotations

import time

import numpy as np

from app.models.entities import AttendanceEvent, CameraDevice
from app.vision.camera.usb_device import (
    UsbDeviceInfo,
    fingerprint_stable_id,
    set_usb_enumerator_for_tests,
)


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


class _FakeCap:
    def __init__(self, frame):
        self._frame = frame
        self.opened = True

    def isOpened(self):
        return self.opened

    def set(self, *_a, **_k):
        return True

    def get(self, _p):
        h, w = self._frame.shape[:2]
        return {3: w, 4: h, 5: 30.0, 6: 0}.get(_p, 0)

    def read(self):
        return True, self._frame.copy()

    def release(self):
        self.opened = False


def test_usb_enumerate_and_configure_no_attendance(app_client):
    client, application = app_client
    headers = _login(client)
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-CI")
    set_usb_enumerator_for_tests(
        type(
            "E",
            (),
            {
                "list_devices": lambda self: [
                    UsbDeviceInfo(
                        stable_id=sid,
                        friendly_name="UGREEN Camera 4K",
                        index_hint=2,
                        ambiguous=False,
                        mapping_verified=True,
                        capture_mapping_verified=True,
                        device_path_fingerprint="synthetic-dpath-fp",
                        note_vi="synthetic",
                    )
                ]
            },
        )()
    )
    def _frame():
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img[:] = (40, 60, 80)
        img[::20, :, :] = 200
        img[:, ::20, :] = 30
        noise = np.random.default_rng(7).integers(0, 50, size=img.shape, dtype=np.uint8)
        return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    application.state.container.usb_open_capture = lambda index, backend: _FakeCap(_frame())
    try:
        enum = client.get("/api/v1/cameras/usb/enumerate", headers=headers)
        assert enum.status_code == 200, enum.text
        body = enum.json()
        assert body["auto_start"] is False
        assert any(d["stable_id"] == sid for d in body["devices"])
        assert "instance_path_redacted" not in body["devices"][0]

        created = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={
                "name": "USB UGREEN synth",
                "host": "",
                "mock_mode": False,
                "source_type": "USB_UVC",
                "credential_action": "keep",
            },
        )
        assert created.status_code == 200, created.text
        cam_id = created.json()["id"]
        assert created.json()["source_type"] == "USB_UVC"

        diag = client.post(
            "/api/v1/cameras/usb/diagnose",
            headers=headers,
            json={"stable_id": sid},
        )
        assert diag.status_code == 200, diag.text
        assert diag.json()["claims_4k"] is False
        assert diag.json()["attendance_written"] is False

        cfg = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cam_id, "stable_id": sid},
        )
        assert cfg.status_code == 200, cfg.text
        assert cfg.json()["source_type"] == "USB_UVC"
        assert cfg.json()["camera_lab_pass"] is False
        assert cfg.json()["attendance_written"] is False
        assert cfg.json()["face_pilot_pass"] is False

        # Reject client index spoof without hashed stable_id
        bad = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cam_id, "stable_id": "index:2"},
        )
        assert bad.status_code == 422

        # Wait briefly for frames; preview must not write attendance
        time.sleep(0.25)
        from sqlalchemy import func, select

        factory = application.state.container.session_factory
        with factory() as session:
            n = session.scalar(select(func.count()).select_from(AttendanceEvent)) or 0
            row = session.get(CameraDevice, cam_id)
            assert row is not None
            assert row.source_type == "USB_UVC"
            assert row.usb_stable_id == sid
        assert int(n) == 0

        health = client.get(f"/api/v1/cameras/gateway/health?camera_id={cam_id}", headers=headers)
        assert health.status_code == 200
        srcs = health.json().get("sources") or []
        assert srcs
        extras = srcs[0].get("extras") or {}
        assert extras.get("source_type") == "USB_UVC" or srcs[0].get("provenance") == "CAMERA_LIVE"
    finally:
        set_usb_enumerator_for_tests(None)
        application.state.container.usb_open_capture = None


def test_usb_configure_revokes_prior_rtsp_material_flag(app_client):
    """Switching RTSP→USB reports material trust invalidation (no EZVIZ HMAC inherit)."""
    client, application = app_client
    headers = _login(client)
    sid = fingerprint_stable_id("USB\\VID_CI&PID_0002\\B")
    set_usb_enumerator_for_tests(
        type(
            "E",
            (),
            {
                "list_devices": lambda self: [
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
            },
        )()
    )
    def _frame2():
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        img[:] = (50, 40, 30)
        img[::15, :, 0] = 220
        noise = np.random.default_rng(3).integers(0, 45, size=img.shape, dtype=np.uint8)
        return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    application.state.container.usb_open_capture = lambda i, b: _FakeCap(_frame2())
    try:
        created = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={
                "name": "Was RTSP",
                "host": "192.168.0.211",
                "rtsp_url_override": "rtsp://192.168.0.211:554/ch1/main",
                "mock_mode": False,
                "source_type": "RTSP",
                "credential_action": "keep",
            },
        )
        assert created.status_code == 200, created.text
        cam_id = created.json()["id"]
        cfg = client.post(
            "/api/v1/cameras/gateway/live/configure-usb",
            headers=headers,
            json={"camera_id": cam_id, "stable_id": sid},
        )
        assert cfg.status_code == 200, cfg.text
        tl = cfg.json().get("trust_lifecycle") or {}
        assert tl.get("material") is True
        assert "source_type" in (tl.get("reasons") or [])
    finally:
        set_usb_enumerator_for_tests(None)
        application.state.container.usb_open_capture = None

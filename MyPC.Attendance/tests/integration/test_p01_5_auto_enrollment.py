"""P01.5 guided auto-enrollment API (synthetic DEMO path)."""

from __future__ import annotations

import base64

import cv2
import numpy as np


def login(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestAdminPass!234"},
    )
    assert r.status_code == 200
    return r.json()["csrf_token"]


def _b64_canvas(salt: int) -> str:
    rng = np.random.default_rng(salt)
    img = np.full((640, 640, 3), 130, dtype=np.uint8)
    img[40:600, 160:480] = rng.integers(80, 190, size=(560, 320, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


FACE = ["FACE_FRONT", "FACE_LEFT", "FACE_RIGHT"]
BODY = ["BODY_FRONT", "BODY_LEFT", "BODY_RIGHT", "BODY_MOTION"]


def test_auto_enrollment_full_demo_flow(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-AUTO", "full_name": "Tự Động Đăng Ký"},
    ).json()

    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "HR-AUTO-1",
            "authorization_ack_vi": "Tôi xác nhận đã thông báo và được phép đăng ký khuôn mặt.",
            "source": "DEMO",
        },
    )
    assert start.status_code == 200, start.text
    sess = start.json()
    assert sess["roi_required"] is False
    sid = sess["session_id"]
    assert "FACE_FRONT" in sess["current_step"] or sess["current_step"] == "FACE_FRONT"

    for i, slot in enumerate(FACE):
        r = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
            headers=headers,
            json={
                "identity_fixture_key": "NV-AUTO",
                "image_base64": _b64_canvas(100 + i),
                "force_slot": slot,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted"] is True, body
        assert slot in body["completed_slots"]

    for i, slot in enumerate(BODY):
        r = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
            headers=headers,
            json={
                "identity_fixture_key": "NV-AUTO",
                "image_base64": _b64_canvas(200 + i),
                "force_slot": slot,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted"] is True, body

    got = client.get(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}",
        headers=headers,
    ).json()
    assert got["face_done"] == 3
    assert got["body_done"] == 4
    assert got["ui_state"] in {"READY_TO_ACTIVATE", "SAMPLE_ACCEPTED", "CHECKING_IDENTITY"}

    act = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/activate",
        headers=headers,
        json={"identity_fixture_key": "NV-AUTO"},
    )
    assert act.status_code == 200, act.text
    assert act.json()["activated"] is True
    assert act.json()["status"] == "ACTIVE" or act.json()["ui_state"] == "ACTIVE"

    verify = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-AUTO", "publish_attendance": True},
    ).json()
    assert verify["outcome"] == "MATCH"
    assert verify.get("attendance_published") is False


def test_auto_real_camera_blocked(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-AUTO-LIVE", "full_name": "Live Auto"},
    ).json()
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "X",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "REAL_CAMERA",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "CAMERA_LAB_BLOCKED"


def test_body_geometry_blocked_honest(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-GEO", "full_name": "Geo Block"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "G",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    sid = start["session_id"]
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={
            "identity_fixture_key": "NV-GEO",
            "force_slot": "BODY_FRONT",
            "declare_body_geometry_blocked": True,
            "image_base64": _b64_canvas(1),
        },
    )
    assert r.status_code == 200
    assert r.json().get("blocked") is True
    assert r.json()["code"] == "BLOCKED_BY_CAMERA_GEOMETRY"


def test_duplicate_frame_rejected(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-DUP", "full_name": "Dup Frame"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "D",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    sid = start["session_id"]
    img = _b64_canvas(42)
    r1 = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={"identity_fixture_key": "NV-DUP", "image_base64": img, "force_slot": "FACE_FRONT"},
    )
    assert r1.status_code == 200
    assert r1.json()["accepted"] is True
    r2 = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={"identity_fixture_key": "NV-DUP", "image_base64": img, "force_slot": "FACE_LEFT"},
    )
    assert r2.status_code == 200
    assert r2.json()["accepted"] is False
    assert r2.json()["code"] == "DUPLICATE_FRAME"

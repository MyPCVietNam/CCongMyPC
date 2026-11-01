"""P01 enrollment / verification API integration (lifecycle + activate)."""

from __future__ import annotations


def login(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestAdminPass!234"},
    )
    assert r.status_code == 200
    return r.json()["csrf_token"]


def test_enrollment_and_verify_fixture_identity(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-FACE", "full_name": "Nguyễn Văn Face"},
    ).json()

    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/start",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "authorization_ref": "HR-2026-001",
            "authorization_ack_vi": "Tôi xác nhận đã thông báo và được phép đăng ký khuôn mặt.",
            "source": "DEMO",
        },
    )
    assert start.status_code == 200, start.text
    body = start.json()
    enr_id = body["enrollment_id"]
    assert body["status"] == "CAPTURING"  # not ACTIVE until activate

    for i in range(3):
        sample = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/{enr_id}/sample",
            headers=headers,
            json={"identity_fixture_key": "NV-FACE", "pose_slot": ["FACE_FRONT", "FACE_LEFT", "FACE_RIGHT"][i]},
        )
        assert sample.status_code == 200, sample.text
        assert sample.json()["accepted"] is True

    # Not published yet
    early = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-FACE"},
    ).json()
    assert early["outcome"] == "UNKNOWN"

    act = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/{enr_id}/activate",
        headers=headers,
        json={"identity_fixture_key": "NV-FACE"},
    )
    assert act.status_code == 200, act.text
    assert act.json()["activated"] is True
    assert act.json()["status"] == "ACTIVE"

    verify = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-FACE", "publish_attendance": True},
    )
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["outcome"] == "MATCH"
    assert body["employee_id"] == emp["id"]
    assert body.get("attendance_published") is False

    unknown = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "STRANGER-99"},
    ).json()
    assert unknown["outcome"] == "UNKNOWN"

    rev = client.delete(
        f"/api/v1/employees/{emp['id']}/enrollment/{enr_id}",
        headers=headers,
    )
    assert rev.status_code == 200
    after = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-FACE"},
    ).json()
    assert after["outcome"] == "UNKNOWN"


def test_failed_reenroll_keeps_old_active(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-KEEP", "full_name": "Giữ Mẫu Cũ"},
    ).json()

    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/start",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "authorization_ref": "A",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    enr1 = start["enrollment_id"]
    for _ in range(3):
        client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/{enr1}/sample",
            headers=headers,
            json={"identity_fixture_key": "NV-KEEP"},
        )
    assert client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/{enr1}/activate",
        headers=headers,
        json={"identity_fixture_key": "NV-KEEP"},
    ).json()["activated"]

    # Start replacement — must NOT revoke old yet
    start2 = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/start",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "authorization_ref": "B",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử hai.",
            "source": "DEMO",
        },
    ).json()
    enr2 = start2["enrollment_id"]
    assert start2["status"] == "CAPTURING"

    still = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-KEEP"},
    ).json()
    assert still["outcome"] == "MATCH"

    # Cancel incomplete replacement
    client.delete(
        f"/api/v1/employees/{emp['id']}/enrollment/{enr2}",
        headers=headers,
    )
    after = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-KEEP"},
    ).json()
    assert after["outcome"] == "MATCH"


def test_real_camera_enrollment_blocked(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-LIVE", "full_name": "Live Block"},
    ).json()
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/start",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "authorization_ref": "X",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "REAL_CAMERA",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "CAMERA_LAB_BLOCKED"


def test_face_status(app_client):
    client, _ = app_client
    login(client)
    r = client.get("/api/v1/face/status")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_invalid_image_rejected(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-BADIMG", "full_name": "Bad Img"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/start",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "authorization_ref": "X",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/{start['enrollment_id']}/sample",
        headers=headers,
        json={"image_base64": "bm90LWFuLWltYWdl"},  # "not-an-image"
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] in {"DECODE_FAILED", "UNSUPPORTED_FORMAT", "TOO_SMALL"}

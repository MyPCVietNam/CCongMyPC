"""P01 enrollment / verification API integration."""

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
    enr_id = start.json()["enrollment_id"]

    for i in range(3):
        sample = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/{enr_id}/sample",
            headers=headers,
            json={"identity_fixture_key": "NV-FACE"},
        )
        assert sample.status_code == 200, sample.text
        assert sample.json()["accepted"] is True

    verify = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "NV-FACE", "publish_attendance": True},
    )
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["outcome"] == "MATCH"
    assert body["employee_id"] == emp["id"]
    assert body.get("attendance_published") is False  # synthetic never becomes REAL

    # Unknown identity
    unknown = client.post(
        "/api/v1/face/verify",
        headers=headers,
        json={"identity_fixture_key": "STRANGER-99"},
    ).json()
    assert unknown["outcome"] == "UNKNOWN"

    # Revoke
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

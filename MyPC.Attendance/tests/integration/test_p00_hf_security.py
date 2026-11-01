"""P00-HF security and hardening tests."""

from __future__ import annotations

import json

from app.core.clock import local_wall
from app.core.permissions import DEMO_MOCK_INGEST
from app.models.entities import User
from sqlalchemy import select


def login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"], r.json()


def test_anonymous_denied(app_client):
    client, _ = app_client
    assert client.get("/api/v1/employees").status_code == 401
    assert client.post("/api/v1/cameras", json={}).status_code == 401


def test_mock_observation_blocked_in_production(prod_client):
    client, app = prod_client
    csrf, _ = login(client)
    # Even if we grant DEMO permission, production settings block the endpoint
    factory = app.state.container.session_factory
    with factory() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        admin.permissions_json = json.dumps([DEMO_MOCK_INGEST])
        session.commit()
    # re-login to refresh session (permissions loaded from DB each request)
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "P1", "full_name": "Prod Block"},
    )
    assert emp.status_code == 200
    r = client.post(
        "/api/v1/attendance/mock-observation",
        headers=headers,
        json={
            "employee_id": emp.json()["id"],
            "work_date": "2026-03-02",
            "observed_at": local_wall(2026, 3, 2, 17, 58).isoformat(),
        },
    )
    assert r.status_code == 403
    assert "production" in r.json()["detail"].lower() or "mô phỏng" in r.json()["detail"].lower()


def test_mock_observation_requires_demo_permission(app_client):
    client, app = app_client
    # Strip DEMO permission
    factory = app.state.container.session_factory
    with factory() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        admin.permissions_json = "[]"
        session.commit()
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "ND", "full_name": "No Demo"},
    )
    # employee create still ok (EMPLOYEE_MANAGE via SYSTEM_ADMIN role)
    assert emp.status_code == 200
    r = client.post(
        "/api/v1/attendance/mock-observation",
        headers=headers,
        json={
            "employee_id": emp.json()["id"],
            "work_date": "2026-03-02",
            "observed_at": local_wall(2026, 3, 2, 17, 58).isoformat(),
        },
    )
    assert r.status_code == 403


def test_roi_validation_rejects_invalid(app_client):
    client, _ = app_client
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "ROI", "mock_mode": True},
    ).json()
    bad = client.put(
        f"/api/v1/cameras/{cam['id']}/regions",
        headers=headers,
        json={"name": "arrival", "x": 0.8, "y": 0.8, "w": 0.5, "h": 0.5},
    )
    assert bad.status_code == 422
    zero = client.put(
        f"/api/v1/cameras/{cam['id']}/regions",
        headers=headers,
        json={"name": "arrival", "x": 0.1, "y": 0.1, "w": 0.0, "h": 0.2},
    )
    assert zero.status_code == 422
    neg = client.put(
        f"/api/v1/cameras/{cam['id']}/regions",
        headers=headers,
        json={"name": "arrival", "x": -0.1, "y": 0.1, "w": 0.2, "h": 0.2},
    )
    assert neg.status_code == 422


def test_camera_host_ssrf_blocked(app_client):
    client, _ = app_client
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    r = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "meta", "host": "169.254.169.254", "mock_mode": False},
    )
    assert r.status_code == 422
    r2 = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "cred-url",
            "mock_mode": False,
            "rtsp_url_override": "rtsp://user:pass@192.168.1.10/stream",
        },
    )
    assert r2.status_code == 422


def test_live_preview_no_silent_mock_substitute(app_client):
    client, _ = app_client
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Live", "host": "192.168.1.50", "mock_mode": False, "username": "u", "password": "p"},
    ).json()
    prev = client.get(f"/api/v1/cameras/{cam['id']}/preview")
    assert prev.status_code == 503
    detail = prev.json()["detail"]
    # P02-HF: live camera without registry bind must fail closed (no silent MOCK)
    assert detail["code"] == "LIVE_NOT_CONFIGURED"
    assert detail.get("camera_lab_pass") is False


def test_csrf_two_sessions_independent(app_client):
    client, _ = app_client
    csrf_a, data_a = login(client)
    # Second login in same TestClient overwrites cookie — simulate via token store
    state = client.app.state.container
    sid_a = data_a["session_id"]
    assert sid_a in state.csrf_by_session
    # Create second session token manually
    from app.core.security import issue_session_token
    import secrets

    sid_b = secrets.token_urlsafe(24)
    from app.api.deps import ensure_csrf

    csrf_b = ensure_csrf(state, sid_b)
    assert csrf_a != csrf_b
    assert state.csrf_by_session[sid_a] == csrf_a
    assert state.csrf_by_session[sid_b] == csrf_b
    # Cross-use must fail
    token_b = issue_session_token(
        state.settings.secret_key,
        {"uid": data_a["user"]["id"], "username": "admin", "role": "SYSTEM_ADMIN", "sid": sid_b},
    )
    client.cookies.set("mypc_session", token_b)
    r = client.post(
        "/api/v1/cameras",
        headers={"X-CSRF-Token": csrf_a},  # wrong session's CSRF
        json={"name": "x", "mock_mode": True},
    )
    assert r.status_code == 403


def test_idempotent_mock_replay(app_client):
    client, _ = app_client
    csrf, _ = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "IDEM", "full_name": "Idempotent"},
    ).json()
    payload = {
        "employee_id": emp["id"],
        "work_date": "2026-03-02",
        "observed_at": local_wall(2026, 3, 2, 17, 58).isoformat(),
        "client_event_id": "fixed-event-key-001",
    }
    r1 = client.post("/api/v1/attendance/mock-observation", headers=headers, json=payload)
    r2 = client.post("/api/v1/attendance/mock-observation", headers=headers, json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True

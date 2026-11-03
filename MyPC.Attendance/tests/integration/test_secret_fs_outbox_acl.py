"""Retry requires SETTINGS_APPLY; unauthenticated diagnostics stay redacted."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.core.permissions import CAMERA_MANAGE, DEMO_MOCK_INGEST, ENROLLMENT_MANAGE
from app.models.entities import User


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_diagnostics_unauthenticated_redacts_outbox_paths(app_client):
    client, _app = app_client
    d = client.get("/api/v1/system/diagnostics")
    assert d.status_code == 200
    body = d.json()
    outbox = body.get("secret_fs_outbox") or {}
    assert "pending_count" in outbox
    # Must not leak journal/file paths or error strings
    assert "pending" not in outbox
    assert "errors" not in outbox
    assert "paths" not in outbox
    blob = json.dumps(body)
    assert "/secrets/" not in blob
    assert "staged-" not in blob
    assert ".bin" not in blob
    assert "last_error" not in outbox


def test_retry_requires_settings_apply(app_client):
    client, app = app_client
    # Strip SETTINGS_APPLY from admin — keep camera manage for login usability
    factory = app.state.container.session_factory
    with factory() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        admin.permissions_json = json.dumps([DEMO_MOCK_INGEST, ENROLLMENT_MANAGE, CAMERA_MANAGE])
        # role admin normally has SETTINGS_APPLY via role map — force restricted role
        admin.role = "operator"
        session.commit()

    headers = _login(client)
    r = client.post("/api/v1/system/secret-fs-outbox/retry", headers=headers)
    assert r.status_code == 403, r.text
    assert "SETTINGS_APPLY" in r.text


def test_retry_ok_with_admin_settings_apply(app_client):
    client, _app = app_client
    headers = _login(client)
    r = client.post("/api/v1/system/secret-fs-outbox/retry", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "recovery" in body
    assert "pending" in body
    # Redacted pending entries only
    for item in body["pending"]:
        assert "staged_ref" not in item
        assert "live_ref" not in item
        assert "last_error" not in item

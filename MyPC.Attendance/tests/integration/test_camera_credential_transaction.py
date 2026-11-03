"""P0-02: credential REPLACE/REMOVE must not mutate live secrets before SQL commit."""

from __future__ import annotations

from unittest import mock

from app.models.entities import CameraDevice
from app.services.secret_fs_outbox import SESSION_KEY


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_replace_stages_then_promotes_after_commit(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "CredReplace",
            "host": "192.168.0.141",
            "username": "admin",
            "password": "OriginalPass!!1",
            "credential_action": "replace",
            "mock_mode": True,
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    secrets = app.state.container.secrets
    live = secrets.live_camera_ref(cid)
    assert secrets.get_camera_secret(live)["password"] == "OriginalPass!!1"

    patched = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "credential_action": "replace",
            "username": "admin",
            "password": "ReplacedPass!!2",
        },
    )
    assert patched.status_code == 200, patched.text
    assert secrets.get_camera_secret(live)["password"] == "ReplacedPass!!2"
    # No leftover staged blobs
    assert list(secrets._dir.glob(f"camera-{cid}.staged-*.bin")) == []


def test_replace_rollback_keeps_original_live_secret(app_client):
    import pytest

    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "CredRollback",
            "host": "192.168.0.142",
            "username": "admin",
            "password": "KeepOriginal!!3",
            "credential_action": "replace",
            "mock_mode": True,
        },
    ).json()["id"]
    secrets = app.state.container.secrets
    live = secrets.live_camera_ref(cid)

    from app.api import cameras as cameras_mod

    real_apply = cameras_mod.apply_camera_credentials

    def apply_then_break(*args, **kwargs):
        real_apply(*args, **kwargs)
        # Simulate failure after staging, before durable commit
        raise RuntimeError("simulated_db_flush_failure")

    with mock.patch.object(cameras_mod, "apply_camera_credentials", side_effect=apply_then_break):
        with pytest.raises(RuntimeError, match="simulated_db_flush_failure"):
            client.patch(
                f"/api/v1/cameras/{cid}",
                headers=headers,
                json={
                    "credential_action": "replace",
                    "username": "admin",
                    "password": "ShouldNotStick!!4",
                },
            )
    assert secrets.get_camera_secret(live)["password"] == "KeepOriginal!!3"
    assert list(secrets._dir.glob(f"camera-{cid}.staged-*.bin")) == []


def test_remove_defers_live_delete_until_commit(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "CredRemove",
            "host": "192.168.0.143",
            "username": "admin",
            "password": "RemoveAfter!!5",
            "credential_action": "replace",
            "mock_mode": True,
        },
    ).json()["id"]
    secrets = app.state.container.secrets
    live = secrets.live_camera_ref(cid)
    assert secrets.has_secret(live)

    deleted: list[str] = []
    real_del = secrets.delete_camera_secret

    def track(ref):
        deleted.append(ref)
        return real_del(ref)

    with mock.patch.object(secrets, "delete_camera_secret", side_effect=track):
        r = client.patch(
            f"/api/v1/cameras/{cid}",
            headers=headers,
            json={"credential_action": "remove"},
        )
    assert r.status_code == 200, r.text
    assert live in deleted
    assert not secrets.has_secret(live)
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row is not None
        assert (row.secret_ref or "") == ""


def test_hard_delete_uses_session_outbox_not_appstate(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HardDelOutbox",
            "host": "192.168.0.144",
            "username": "admin",
            "password": "HardDel!!6",
            "credential_action": "replace",
            "mock_mode": True,
        },
    ).json()["id"]
    secrets = app.state.container.secrets
    live = secrets.live_camera_ref(cid)
    # Ensure AppState no longer carries a global pending list
    assert not hasattr(app.state.container, "pending_camera_secret_deletes") or not getattr(
        app.state.container, "pending_camera_secret_deletes", None
    )
    r = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json().get("credential_delete_deferred") is True
    assert not secrets.has_secret(live)

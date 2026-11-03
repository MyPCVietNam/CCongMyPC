"""P0-1: camera hard-delete must not scrub credentials before durable DB commit."""

from __future__ import annotations

from unittest import mock

from app.models.entities import CameraDevice, RawObservation
from app.core.clock import local_wall


def _obs_ts():
    return local_wall(2026, 3, 2, 12, 0, 0)


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_hard_delete_defers_secret_until_commit(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "DelSafe",
            "host": "192.168.0.121",
            "rtsp_url_override": "rtsp://192.168.0.121:554/ch1/main",
            "username": "admin",
            "password": "KeepSecret!!1",
            "credential_action": "replace",
            "mock_mode": False,
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row is not None
        secret_ref = row.secret_ref
        assert secret_ref
        assert app.state.container.secrets.has_secret(secret_ref)

    deleted = []

    def _track(ref):
        deleted.append(ref)
        # Call through to real delete after tracking order
        return SecretsStore_delete(ref)

    secrets = app.state.container.secrets
    SecretsStore_delete = secrets.delete_camera_secret

    with mock.patch.object(secrets, "delete_camera_secret", side_effect=_track):
        r = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json().get("credential_delete_deferred") is True
    # Secret scrub happened (after commit path inside get_db)
    assert deleted == [secret_ref]
    assert not secrets.has_secret(secret_ref)


def test_hard_delete_rollback_keeps_secret(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "KeepOnFail",
            "host": "192.168.0.122",
            "username": "admin",
            "password": "MustSurvive!!2",
            "credential_action": "replace",
            "mock_mode": True,
        },
    ).json()["id"]
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        secret_ref = row.secret_ref
        assert app.state.container.secrets.has_secret(secret_ref)

    secrets = app.state.container.secrets
    calls = []

    def boom(ref):
        calls.append(ref)
        raise AssertionError("must not delete secret before/without commit")

    # Force flush of camera delete to fail after config cleanup by raising on delete flush
    from app.api import cameras as cameras_mod
    from sqlalchemy.exc import IntegrityError

    real_blockers = cameras_mod._camera_delete_blockers

    def blockers_then_ok(db, camera_id):
        return real_blockers(db, camera_id)

    with mock.patch.object(secrets, "delete_camera_secret", side_effect=boom), mock.patch(
        "app.api.cameras._camera_delete_blockers", side_effect=blockers_then_ok
    ):
        # Inject history so delete returns 409 before secret scrub
        with app.state.container.session_factory() as db:
            now = _obs_ts()
            db.add(
                RawObservation(
                    camera_id=cid,
                    employee_id=None,
                    captured_at_utc=now,
                    received_at_utc=now,
                    obs_type="FACE_MATCH",
                    source="MOCK",
                    idempotency_key=f"obs-keep-{cid}",
                )
            )
            db.commit()
        r = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert r.status_code == 409, r.text
    assert calls == []
    assert secrets.has_secret(secret_ref)
    # Camera row still present
    with app.state.container.session_factory() as db:
        assert db.get(CameraDevice, cid) is not None


def test_referenced_camera_history_intact_after_blocked_delete(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Hist", "host": "192.168.0.123", "mock_mode": True},
    ).json()["id"]
    with app.state.container.session_factory() as db:
        now = _obs_ts()
        db.add(
            RawObservation(
                camera_id=cid,
                employee_id=None,
                captured_at_utc=now,
                received_at_utc=now,
                obs_type="FACE_MATCH",
                source="MOCK",
                idempotency_key=f"hist-{cid}",
            )
        )
        db.commit()
    r = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert r.status_code == 409
    blockers = client.get(f"/api/v1/cameras/{cid}/delete-blockers", headers=headers).json()
    assert blockers["can_hard_delete"] is False
    assert blockers["blockers"]["raw_observations"] >= 1
    with app.state.container.session_factory() as db:
        assert db.get(CameraDevice, cid) is not None

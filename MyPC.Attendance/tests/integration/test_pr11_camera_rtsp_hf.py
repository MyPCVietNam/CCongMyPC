"""PR11-HF: camera CRUD, credential reuse, archive, RTSP status honesty."""

from __future__ import annotations

from sqlalchemy import select

from app.models.entities import AuditLog, CameraDevice, RawObservation, User
from app.services.camera_credential_service import apply_camera_credentials, safe_rtsp_uri_for_edit
from app.core.clock import local_wall


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_cm01_get_detail_loads_safe_fields(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "Cam12",
            "host": "192.168.0.211",
            "rtsp_url_override": "rtsp://192.168.0.211:554/ch1/main",
            "username": "admin",
            "password": "CamSecret!99",
            "mock_mode": False,
            "credential_action": "replace",
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    detail = client.get(f"/api/v1/cameras/{cid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Cam12"
    assert body["host"] == "192.168.0.211"
    assert body["rtsp_uri_safe"] == "rtsp://192.168.0.211:554/ch1/main"
    assert "@" not in body["rtsp_uri_safe"]
    assert body["username_hint"] == "admin"
    assert body["has_secret"] is True
    assert body["password"] is None
    assert "CamSecret" not in detail.text


def test_cm05_cm06_blank_password_keeps_secret(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "KeepSecret",
            "host": "192.168.0.50",
            "rtsp_url_override": "rtsp://192.168.0.50:554/ch1/main",
            "username": "admin",
            "password": "OriginalSecret1",
            "credential_action": "replace",
            "mock_mode": False,
        },
    ).json()
    cid = created["id"]
    # PATCH with username + blank password + keep
    upd = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "name": "KeepSecret2",
            "username": "admin",
            "password": "",
            "credential_action": "keep",
        },
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["has_secret"] is True
    # LIVE configure with username + no password field must reuse
    live = client.post(
        "/api/v1/cameras/gateway/live/configure",
        headers=headers,
        json={
            "camera_id": cid,
            "rtsp_uri": "rtsp://192.168.0.50:554/ch1/main",
            "username": "admin",
            "credential_action": "keep",
        },
    )
    # May fail open/decode on Linux without camera — but must NOT wipe secret
    assert live.status_code in (200, 422, 500), live.text
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row is not None
        assert row.secret_ref
        stored = app.state.container.secrets.get_camera_secret(row.secret_ref)
        assert stored is not None
        assert stored["password"] == "OriginalSecret1"


def test_cm07_explicit_replace_password(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "ReplacePw",
            "host": "192.168.0.51",
            "rtsp_url_override": "rtsp://192.168.0.51:554/ch1/main",
            "username": "admin",
            "password": "FirstPass!!1",
            "credential_action": "replace",
        },
    ).json()["id"]
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "username": "admin",
            "password": "SecondPass!!2",
            "credential_action": "replace",
        },
    )
    assert r.status_code == 200
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        stored = app.state.container.secrets.get_camera_secret(row.secret_ref)
        assert stored["password"] == "SecondPass!!2"


def test_cm09_cm11_archive_and_restore(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "ArchiveMe", "host": "192.168.0.52", "mock_mode": True},
    ).json()["id"]
    ar = client.post(f"/api/v1/cameras/{cid}/archive", headers=headers, json={})
    assert ar.status_code == 200
    listed = client.get("/api/v1/cameras").json()
    assert all(c["id"] != cid for c in listed)
    restored = client.post(f"/api/v1/cameras/{cid}/restore", headers=headers, json={})
    assert restored.status_code == 200
    listed2 = client.get("/api/v1/cameras").json()
    assert any(c["id"] == cid for c in listed2)


def test_cm10_history_blocks_hard_delete(app_client, frozen_clock):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "HistCam", "host": "192.168.0.53", "mock_mode": True},
    ).json()["id"]
    with app.state.container.session_factory() as db:
        db.add(
            RawObservation(
                camera_id=cid,
                employee_id=None,
                captured_at_utc=frozen_clock.now_utc(),
                received_at_utc=frozen_clock.now_utc(),
                obs_type="FACE_MATCH",
                source="MOCK",
                idempotency_key=f"hist-{cid}",
            )
        )
        db.commit()
    doomed = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert doomed.status_code == 409
    detail = doomed.json()["detail"]
    assert detail["code"] == "CAMERA_HAS_HISTORY"
    # Still present
    assert client.get(f"/api/v1/cameras/{cid}").status_code == 200


def test_cm03_duplicate_host_path_rejected(app_client):
    client, _ = app_client
    headers = _login(client)
    payload = {
        "name": "DupA",
        "host": "192.168.0.54",
        "rtsp_url_override": "rtsp://192.168.0.54:554/ch1/main",
        "mock_mode": True,
    }
    assert client.post("/api/v1/cameras", headers=headers, json=payload).status_code == 200
    dup = client.post("/api/v1/cameras", headers=headers, json={**payload, "name": "DupB"})
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "CAMERA_DUPLICATE"


def test_rt09_configure_reports_config_saved_not_live(app_client):
    client, _ = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "LiveCfg",
            "host": "192.168.0.55",
            "rtsp_url_override": "rtsp://192.168.0.55:554/ch1/main",
            "username": "admin",
            "password": "WhateverPass1",
            "credential_action": "replace",
            "mock_mode": False,
        },
    ).json()["id"]
    live = client.post(
        "/api/v1/cameras/gateway/live/configure",
        headers=headers,
        json={
            "camera_id": cid,
            "rtsp_uri": "rtsp://192.168.0.55:554/ch1/main",
            "credential_action": "keep",
        },
    )
    assert live.status_code == 200, live.text
    body = live.json()
    assert body["live_verified"] is False
    assert body["connection_status"] == "CONFIG_SAVED"
    assert body["camera_lab_pass"] is False


def test_rt01_tcp_probe_not_camera_lab(app_client):
    client, _ = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "Probe",
            "host": "127.0.0.1",  # will fail host validation — use LAN
        },
    )
    # 127.0.0.1 blocked by SSRF policy
    assert cid.status_code == 422
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "Probe",
            "host": "192.168.0.211",
            "rtsp_url_override": "rtsp://192.168.0.211:554/ch1/main",
            "username": "admin",
            "password": "x",
            "credential_action": "replace",
        },
    ).json()["id"]
    probe = client.post(
        f"/api/v1/cameras/{cid}/rtsp/test",
        headers=headers,
        json={"rtsp_uri": "rtsp://192.168.0.211:554/ch1/main"},
    )
    assert probe.status_code == 200
    body = probe.json()
    assert body["camera_lab_pass"] is False
    assert body["secrets_redacted"] is True


def test_credential_helper_blank_does_not_wipe():
    class FakeSecrets:
        def __init__(self):
            self.data = {"camera-1.bin": {"username": "u", "password": "p"}}

        def live_camera_ref(self, camera_id):
            return f"camera-{int(camera_id)}.bin"

        def put_camera_secret(self, camera_id, username, password):
            self.data[f"camera-{camera_id}.bin"] = {
                "username": username,
                "password": password,
            }
            return f"camera-{camera_id}.bin"

        def stage_camera_secret(self, camera_id, username, password):
            ref = f"camera-{camera_id}.staged-test.bin"
            self.data[ref] = {"username": username, "password": password}
            return ref

        def get_camera_secret(self, ref):
            return self.data.get(ref)

        def delete_camera_secret(self, ref):
            self.data.pop(ref, None)

    s = FakeSecrets()
    r = apply_camera_credentials(
        s,
        camera_id=1,
        current_secret_ref="camera-1.bin",
        current_username_hint="u",
        action="keep",
        username="u",
        password="",
    )
    assert r.changed is False
    assert s.data["camera-1.bin"]["password"] == "p"
    assert safe_rtsp_uri_for_edit("rtsp://user:pass@192.168.0.1:554/ch1/main") == (
        "rtsp://192.168.0.1:554/ch1/main"
    )


def test_cm12_csrf_and_permission(app_client):
    client, _ = app_client
    # no login
    assert client.post("/api/v1/cameras", json={"name": "x"}).status_code == 401
    headers = _login(client)
    assert (
        client.post("/api/v1/cameras", json={"name": "x"}).status_code == 403
    )  # missing CSRF
    assert client.post("/api/v1/cameras", headers=headers, json={"name": "ok"}).status_code == 200


def test_cm16_audit_no_secrets(app_client):
    client, app = app_client
    headers = _login(client)
    client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "Aud",
            "host": "192.168.0.56",
            "username": "admin",
            "password": "SuperSecret99",
            "credential_action": "replace",
        },
    )
    with app.state.container.session_factory() as db:
        logs = db.scalars(select(AuditLog).where(AuditLog.action == "CAMERA_CREATE")).all()
        assert logs
        blob = " ".join((l.reason or "") + (l.action or "") for l in logs)
        assert "SuperSecret99" not in blob

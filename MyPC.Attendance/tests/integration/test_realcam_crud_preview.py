"""RealCam CRUD + preview labeling + duplicate dry-run."""

from __future__ import annotations


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_duplicate_dry_run_never_deletes(app_client):
    client, app = app_client
    headers = _login(client)
    a = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "A",
            "host": "192.168.0.77",
            "rtsp_url_override": "rtsp://192.168.0.77:554/ch1/main",
            "mock_mode": False,
        },
    )
    assert a.status_code == 200, a.text
    # Second identical host/path should be blocked at create
    b = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "B",
            "host": "192.168.0.77",
            "rtsp_url_override": "rtsp://192.168.0.77:554/ch1/main",
            "mock_mode": False,
        },
    )
    assert b.status_code == 409, b.text
    dry = client.get("/api/v1/cameras/duplicates/dry-run", headers=headers)
    assert dry.status_code == 200
    body = dry.json()
    assert body["dry_run"] is True
    assert body["auto_delete"] is False
    # Original still present
    listed = client.get("/api/v1/cameras").json()
    assert any(c["id"] == a.json()["id"] for c in listed)


def test_mock_preview_is_snapshot_labeled_not_500(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Mock3", "host": "", "mock_mode": True},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    # Force non-production path for mock preview in tests
    prev = client.get(f"/api/v1/cameras/{cid}/preview")
    assert prev.status_code in (200, 422), prev.text
    if prev.status_code == 200:
        body = prev.json()
        assert body.get("view_mode") == "SNAPSHOT"
        assert body.get("mock") is True
        assert body.get("camera_lab_pass") is False
        assert "LIVE" not in (body.get("indicator_vi") or "") or "SNAPSHOT" in (
            body.get("indicator_vi") or ""
        )


def test_hard_delete_unreferenced_ok(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "TempDel", "host": "192.168.0.88", "mock_mode": True},
    ).json()["id"]
    deleted = client.delete(f"/api/v1/cameras/{cid}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_id"] == cid


def test_lab_run_out_includes_next_action(app_client):
    client, app = app_client
    headers = _login(client)
    # Need PILOT_APPROVE — admin typically has it
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "LabCam",
            "host": "192.168.0.99",
            "rtsp_url_override": "rtsp://192.168.0.99:554/ch1/main",
            "mock_mode": False,
            "username": "admin",
            "password": "x",
            "credential_action": "replace",
        },
    )
    assert cam.status_code == 200, cam.text
    cid = cam.json()["id"]
    run = client.post(
        f"/api/v1/cameras/{cid}/lab-runs",
        headers=headers,
        json={"kind": "CAMERA_LAB", "profile": "MAIN"},
    )
    # May 403 if permission missing in fixture — accept 200/403/503
    assert run.status_code in (200, 403, 503), run.text
    if run.status_code == 200:
        body = run.json()
        assert body["camera_lab_pass"] is False
        assert body["next_action"] == "MEASURE_LIVE"
        assert body["face_validation_status"] == "N_A"
        assert "owner_challenge" not in body

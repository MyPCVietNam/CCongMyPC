"""P02-HF/P02Q camera preview registry + quality APIs — INTEGRATION (no physical camera)."""

from __future__ import annotations


def _login(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_mock_preview_uses_registry_and_quality_endpoints(app_client):
    client, app = app_client
    headers = _login(client)
    # Create mock camera
    r = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Mock Cam", "host": "", "mock_mode": True, "enabled": True},
    )
    assert r.status_code == 200, r.text
    cam_id = r.json()["id"]

    prev = client.get(f"/api/v1/cameras/{cam_id}/preview")
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["mock"] is True
    assert body["provenance"] == "MOCK"
    assert body["size_source"] == "DECODED_MEASURED"
    assert body["camera_lab_pass"] is False
    assert body["pixel_sha256"]
    assert body["config_revision"]

    # Same revision bound in registry
    reg = app.state.container.camera_registry
    bound = reg.get(cam_id)
    assert bound is not None
    assert bound.config_revision == body["config_revision"]

    q = client.get(f"/api/v1/cameras/{cam_id}/quality/diagnostics")
    assert q.status_code == 200
    qd = q.json()
    assert qd["camera_lab_pass"] is False
    assert qd["auto_enhance"]["effective"] == "AUTO_TEST_ONLY"
    assert qd["vendor_spec"]["status"] == "VENDOR_SPEC"

    an = client.post(f"/api/v1/cameras/{cam_id}/quality/analyze-once", headers=headers, json={})
    assert an.status_code == 200, an.text
    assert an.json()["original_unchanged"] is True
    assert an.json()["effective_mode"] == "AUTO_TEST_ONLY"
    assert an.json().get("paired") is not None
    assert an.json()["paired"].get("can_auto_enable_enhancement") is False

    # LIVE configure must reject credential-in-URI
    bad = client.post(
        "/api/v1/cameras/gateway/live/configure",
        headers=headers,
        json={
            "camera_id": cam_id,
            "rtsp_uri": "rtsp://admin:pass@192.168.1.50:554/stream",
            "profile": "MAIN",
        },
    )
    assert bad.status_code == 422

    # Settings default + put stays AUTO_TEST_ONLY without pilot confirmation
    s = client.get(f"/api/v1/cameras/{cam_id}/quality/settings")
    assert s.status_code == 200
    put = client.put(
        f"/api/v1/cameras/{cam_id}/quality/settings",
        headers=headers,
        json={"requested_mode": "AUTO"},
    )
    assert put.status_code == 200
    assert put.json()["effective_mode"] == "AUTO_TEST_ONLY"

    report = client.get(f"/api/v1/cameras/{cam_id}/quality/report")
    assert report.status_code == 200
    assert "REDACTED" in report.json()["diagnostic_label"]
    assert report.json()["camera_lab_pass"] is False


def test_live_not_configured_no_silent_mock(app_client):
    client, app = app_client
    headers = _login(client)
    r = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "Live Cam",
            "host": "192.168.1.77",
            "mock_mode": False,
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    cam_id = r.json()["id"]
    prev = client.get(f"/api/v1/cameras/{cam_id}/preview")
    assert prev.status_code == 503
    detail = prev.json()["detail"]
    assert detail["code"] == "LIVE_NOT_CONFIGURED"
    assert detail["camera_lab_pass"] is False

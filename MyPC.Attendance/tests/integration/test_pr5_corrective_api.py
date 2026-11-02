"""PR5 corrective API regressions — INTEGRATION."""

from __future__ import annotations

import pytest

from app.vision.camera.gateway import DecoderStatus, MockFrameGateway, StreamProvenance
from app.vision.camera.registry import CameraSourceRegistry, FrameAccessError


def _login(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_auto_validated_json_flag_rejected(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Q", "mock_mode": True},
    ).json()
    r = client.put(
        f"/api/v1/cameras/{cam['id']}/quality/settings",
        headers=headers,
        json={
            "requested_mode": "AUTO_VALIDATED",
            "admin_confirm_live_pilot": True,
            "model_hash_pin": "m",
            "gallery_revision_pin": "g",
            "threshold_id_pin": "t",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "UNSIGNED_APPROVAL_REJECTED"


def test_quality_settings_default_test_only(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Q2", "mock_mode": True},
    ).json()
    r = client.put(
        f"/api/v1/cameras/{cam['id']}/quality/settings",
        headers=headers,
        json={"requested_mode": "AUTO"},
    )
    assert r.status_code == 200
    assert r.json()["effective_mode"] == "AUTO_TEST_ONLY"


def test_gateway_health_ready_false_for_mock(app_client):
    client, _app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "M", "mock_mode": True},
    ).json()
    assert client.get(f"/api/v1/cameras/{cam['id']}/preview").status_code == 200
    h = client.get("/api/v1/cameras/gateway/health", params={"camera_id": cam["id"]})
    assert h.status_code == 200
    body = h.json()
    assert body["camera_lab_pass"] is False
    assert body.get("ready") is False
    sources = body.get("sources") or []
    assert sources and sources[0]["operationally_ready"] is False


def test_stale_or_mock_rejected_for_biometric(app_client):
    _client, app = app_client
    reg: CameraSourceRegistry = app.state.container.camera_registry
    gw = MockFrameGateway(camera_id="99")
    gw.start()
    reg.bind(99, gw, provenance=StreamProvenance.MOCK, profile="MOCK")
    fr = gw.get_latest_frame()
    assert fr is not None
    gw._latest = fr.with_status(DecoderStatus.STALE)  # type: ignore[attr-defined]
    with pytest.raises(FrameAccessError) as ei:
        reg.get_frame(99, allow_mock=True, for_biometric=True, allow_stale=False)
    assert ei.value.code in {
        "STALE_FRAME",
        "BIOMETRIC_REQUIRES_LIVE",
        "MOCK_NOT_ALLOWED",
        "LIVE_REQUIRED",
    }
    gw.stop()


def test_live_observe_shadow_requires_live(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "L", "host": "192.168.1.40", "mock_mode": False},
    ).json()
    r = client.post(f"/api/v1/cameras/{cam['id']}/live/observe-shadow", headers=headers, json={})
    assert r.status_code == 503


def test_report_download_attachment(app_client):
    client, _ = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "R", "mock_mode": True},
    ).json()
    r = client.get(f"/api/v1/cameras/{cam['id']}/quality/report?download=true")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "password" not in r.text.lower()
    assert "rtsp://" not in r.text.lower()

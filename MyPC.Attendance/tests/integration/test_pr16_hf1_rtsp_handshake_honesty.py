"""PR16-HF1: RTSP handshake must not clobber LIVE operational DB status on UNKNOWN."""

from __future__ import annotations

from unittest import mock

from app.models.entities import CameraDevice
from app.vision.camera.rtsp_probe import ProbeStage, RtspProbeResult


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _make_cam(client, headers, host="192.168.0.211"):
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF1Probe",
            "host": host,
            "rtsp_url_override": f"rtsp://{host}:554/ch1/main",
            "username": "admin",
            "password": "CamSecret!99",
            "credential_action": "replace",
            "mock_mode": False,
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _probe(overall: str, stages=None) -> RtspProbeResult:
    return RtspProbeResult(
        camera_id=1,
        config_revision="rev",
        stages=stages
        or [
            ProbeStage(name="TCP", status="OK", detail_vi="ok"),
            ProbeStage(name="OPTIONS", status="OK", detail_vi="ok"),
            ProbeStage(name="DESCRIBE", status="OK", detail_vi="ok"),
        ],
        overall_status=overall,
        secrets_redacted=True,
        camera_lab_pass=False,
    )


def test_unknown_handshake_does_not_clobber_config_saved(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _make_cam(client, headers)
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row.connection_status == "CONFIG_SAVED"
        prior = row.connection_status

    with mock.patch(
        "app.vision.camera.rtsp_probe.probe_rtsp_stages",
        return_value=_probe("UNKNOWN"),
    ):
        r = client.post(
            f"/api/v1/cameras/{cid}/rtsp/test",
            headers=headers,
            json={"rtsp_uri": "rtsp://192.168.0.211:554/ch1/main"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handshake_only"] is True
    assert body["rtsp_handshake_status"] == "UNKNOWN"
    assert body["handshake_inconclusive"] is True
    assert body["connection_status_clobbered"] is False
    assert body["connection_status_persisted"] == prior

    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row.connection_status == "CONFIG_SAVED"
        assert row.last_health_status == "HANDSHAKE:UNKNOWN"


def test_auth_failed_does_persist_when_not_live(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _make_cam(client, headers, host="192.168.0.212")
    with mock.patch(
        "app.vision.camera.rtsp_probe.probe_rtsp_stages",
        return_value=_probe(
            "AUTH_FAILED",
            stages=[ProbeStage(name="DESCRIBE", status="AUTH_FAILED", detail_vi="401", code="401")],
        ),
    ):
        r = client.post(
            f"/api/v1/cameras/{cid}/rtsp/test",
            headers=headers,
            json={"rtsp_uri": "rtsp://192.168.0.212:554/ch1/main"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["connection_status_clobbered"] is True
    assert body["connection_status_persisted"] == "AUTH_FAILED"
    assert body["rtsp_handshake_status"] == "AUTH_FAILED"
    with app.state.container.session_factory() as db:
        assert db.get(CameraDevice, cid).connection_status == "AUTH_FAILED"


def test_auth_failed_does_not_clobber_when_live_healthy(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _make_cam(client, headers, host="192.168.0.215")
    # Simulate independently healthy LIVE decoder in registry health()
    fake_health = {
        "sources": [
            {
                "camera_id": cid,
                "operationally_ready": True,
                "decoder_status": "OK",
            }
        ]
    }

    class _Reg:
        def health(self, camera_db_id=None):
            return fake_health

    app.state.container.camera_registry = _Reg()  # type: ignore[attr-defined]
    with mock.patch(
        "app.vision.camera.rtsp_probe.probe_rtsp_stages",
        return_value=_probe("AUTH_FAILED"),
    ):
        r = client.post(
            f"/api/v1/cameras/{cid}/rtsp/test",
            headers=headers,
            json={"rtsp_uri": "rtsp://192.168.0.215:554/ch1/main"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["rtsp_handshake_status"] == "AUTH_FAILED"
    assert body["live_decoder_operational"] is True
    assert body["connection_status_clobbered"] is False
    assert body["live_status_preserved"] is True
    assert body["connection_status_persisted"] == "CONFIG_SAVED"
    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        assert row.connection_status == "CONFIG_SAVED"
        assert row.last_health_status == "HANDSHAKE:AUTH_FAILED"


def test_stream_not_found_persists(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _make_cam(client, headers, host="192.168.0.213")
    with mock.patch(
        "app.vision.camera.rtsp_probe.probe_rtsp_stages",
        return_value=_probe("STREAM_NOT_FOUND"),
    ):
        r = client.post(
            f"/api/v1/cameras/{cid}/rtsp/test",
            headers=headers,
            json={"rtsp_uri": "rtsp://192.168.0.213:554/missing"},
        )
    assert r.status_code == 200
    assert r.json()["connection_status_persisted"] == "STREAM_NOT_FOUND"


def test_handshake_ok_with_simulated_live_flag(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _make_cam(client, headers, host="192.168.0.214")
    # CONFIG_SAVED stays; handshake OK; live_decoder_operational may be false without registry bind
    with mock.patch(
        "app.vision.camera.rtsp_probe.probe_rtsp_stages",
        return_value=_probe("CONFIG_SAVED"),
    ):
        r = client.post(
            f"/api/v1/cameras/{cid}/rtsp/test",
            headers=headers,
            json={"rtsp_uri": "rtsp://192.168.0.214:554/ch1/main"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["handshake_only"] is True
    assert body["connection_status_clobbered"] is False
    assert body["connection_status_persisted"] == "CONFIG_SAVED"
    assert "live_decoder_operational" in body

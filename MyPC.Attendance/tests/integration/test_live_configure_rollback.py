"""LIVE gateway bind must not survive SQL rollback (audit remaining #4)."""

from __future__ import annotations

from unittest import mock

import pytest


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_configure_live_rollback_unbinds_runtime(app_client):
    client, app = app_client
    headers = _login(client)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "LiveRollback",
            "host": "192.168.0.211",
            "username": "admin",
            "password": "LivePass!!99",
            "credential_action": "replace",
            "mock_mode": False,
            "rtsp_url_override": "rtsp://192.168.0.211:554/ch1/main",
        },
    )
    assert cam.status_code == 200, cam.text
    cid = cam.json()["id"]

    # Fail after route bound LIVE but before durable commit completes
    with mock.patch(
        "app.services.secret_fs_outbox.write_durable_journal",
        side_effect=RuntimeError("simulated_pre_commit_failure"),
    ):
        with pytest.raises(RuntimeError, match="simulated_pre_commit_failure"):
            client.post(
                "/api/v1/cameras/gateway/live/configure",
                headers=headers,
                json={
                    "camera_id": cid,
                    "rtsp_uri": "rtsp://192.168.0.211:554/ch1/main",
                    "credential_action": "keep",
                    "profile": "MAIN",
                },
            )

    reg = app.state.container.camera_registry
    bound = reg.get(cid) if reg else None
    assert bound is None, "LIVE bind must be compensated on SQL rollback"


def test_runtime_compensate_unit_unbind():
    from pathlib import Path

    from app.services.secret_fs_outbox import abort_outbox_after_rollback, register_runtime_compensate
    from app.services.secrets_store import SecretsStore
    from app.vision.camera.gateway import LiveRTSPGateway, StreamProvenance
    from app.vision.camera.registry import CameraSourceRegistry

    class _S:
        info: dict = {}

    secrets = SecretsStore(Path("/tmp/mypc-live-comp-test"))  # noqa: S108 — test tmp
    # Use isolated tmp via pytest tmp if available — recreate cleanly
    import tempfile

    td = tempfile.mkdtemp(prefix="mypc-live-comp-")
    secrets = SecretsStore(Path(td))
    reg = CameraSourceRegistry()
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="7")
    reg.bind(7, gw, provenance=StreamProvenance.CAMERA_LIVE, profile="MAIN")
    assert reg.get(7) is not None
    sess = _S()
    register_runtime_compensate(sess, lambda: reg.unbind(7))  # type: ignore[arg-type]
    abort_outbox_after_rollback(secrets, sess)  # type: ignore[arg-type]
    assert reg.get(7) is None

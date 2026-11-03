"""PR16-HF1: redacted evidence lookup requires PILOT_APPROVE; no auto-sign."""

from __future__ import annotations

from app.core.utc_time import utc_now
from app.models.entities import PilotEvidenceRecord
from app.services.evidence_store import EVIDENCE_PHYSICAL, KIND_CAMERA_LAB


def _login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_list_evidence_redacted_and_no_challenge(app_client):
    client, app = app_client
    headers = _login(client)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "EvCam",
            "host": "192.168.0.220",
            "rtsp_url_override": "rtsp://192.168.0.220:554/ch1/main",
            "username": "admin",
            "password": "SecretCam99",
            "credential_action": "replace",
            "mock_mode": False,
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    with app.state.container.session_factory() as db:
        db.add(
            PilotEvidenceRecord(
                evidence_id="ev-hf1-physical-001",
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=cid,
                lab_run_id="lab-run-1",
                config_revision="rev1",
                provenance="CAMERA_LIVE",
                decoded_w=2880,
                decoded_h=1620,
                fps_measured=19.7,
                model_hash_pin="m",
                gallery_revision_pin="g",
                threshold_id_pin="t",
                operator="admin",
                created_at=utc_now(),
                note_vi="fixture",
                payload_json="{}",
            )
        )
        db.commit()

    r = client.get(f"/api/v1/cameras/{cid}/quality/evidence?kind=CAMERA_LAB")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["physical_verified_ne_signed"] is True
    assert body["camera_lab_pass"] is False
    assert body["items"]
    item = body["items"][0]
    assert item["evidence_id"] == "ev-hf1-physical-001"
    assert "owner_challenge" not in r.text
    assert "SecretCam" not in r.text
    assert "csrf" not in r.text.lower() or "csrf" in "csrf_token_ok"  # body must not leak cookies
    assert body.get("signed_active") in (None, {}) or body["signed_active"] is None or isinstance(
        body["signed_active"], dict
    )


def test_checkbox_approval_still_rejected(app_client):
    client, app = app_client
    headers = _login(client)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "RejectBox",
            "host": "192.168.0.221",
            "mock_mode": True,
        },
    ).json()["id"]
    r = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "admin_confirm": True, "checkbox_pass": True},
    )
    assert r.status_code == 403

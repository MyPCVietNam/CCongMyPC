"""PR16-HF5: effective credential mutation + AUTO_VALIDATED AB recheck (HTTP/DB)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.utc_time import utc_now
from app.models.entities import (
    AbEvaluationRun,
    CameraDevice,
    CameraLabRun,
    CameraLiveBinding,
    PilotApprovalRecord,
    PilotEvidenceRecord,
)
from app.services.evidence_store import EVIDENCE_PHYSICAL, KIND_CAMERA_LAB, ab_run_promotable
from app.services.pilot_approval import issue_approval, verify_active_approval
from app.services.server_pins import derive_live_pins


def _login(client):
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"}
    )
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _pins(app):
    with app.state.container.session_factory() as db:
        pins, _ = derive_live_pins(
            db,
            pipeline=app.state.container.face_pipeline,
            store=app.state.container.template_store,
        )
        return pins


def _seed_signed(app, *, camera_id: int, rev: str, pins: dict[str, str], tag: str = "a"):
    now = utc_now()
    run_id = f"run-hf5-{camera_id}-{tag}"
    evid = f"ev-hf5-{camera_id}-{tag}"
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, camera_id)
        cam.config_revision = rev
        cam.enabled = True
        cam.mock_mode = False
        binding = db.scalar(
            select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_id)
        )
        if binding is None:
            binding = CameraLiveBinding(camera_id=camera_id)
            db.add(binding)
        binding.config_revision = rev
        binding.enabled = True
        binding.host = cam.host or "192.168.0.211"
        binding.port = 554
        binding.path = "/ch1/main"
        db.add(
            CameraLabRun(
                run_id=run_id,
                nonce=f"nonce-hf5-{camera_id}-{tag}",
                kind=KIND_CAMERA_LAB,
                camera_id=camera_id,
                state="PHYSICAL_VERIFIED",
                revoked=False,
                config_revision=rev,
                provenance="CAMERA_LIVE",
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                decoded_w=640,
                decoded_h=360,
                started_at=now,
                expires_at=now + timedelta(hours=7),
            )
        )
        db.add(
            PilotEvidenceRecord(
                evidence_id=evid,
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=camera_id,
                lab_run_id=run_id,
                config_revision=rev,
                provenance="CAMERA_LIVE",
                decoded_w=640,
                decoded_h=360,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                operator="admin",
                created_at=now,
                payload_json="{}",
            )
        )
        issue_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=camera_id,
            issued_by="admin",
            evidence_id=evid,
            **pins,
        )
        db.commit()
    return evid


def _create_cam(client, headers, *, name: str, host: str) -> int:
    r = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": name,
            "host": host,
            "rtsp_url_override": f"rtsp://{host}:554/ch1/main",
            "username": "admin",
            "password": "SyntheticOldPass1!",
            "credential_action": "replace",
            "mock_mode": False,
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_http_keep_plus_password_invalidates_hmac(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = _create_cam(client, headers, name="HF5KeepPwd", host="192.168.0.221")
    evid = _seed_signed(app, camera_id=cid, rev="rev-keep-pwd", pins=pins, tag="kp")
    secrets = app.state.container.secrets
    old = secrets.get_camera_secret(f"camera-{cid}.bin")
    assert old and old.get("password") == "SyntheticOldPass1!"

    with app.state.container.session_factory() as db:
        assert verify_active_approval(
            db, secret_key=app.state.container.settings.secret_key, kind="CAMERA_LAB", camera_id=cid, **pins
        )

    patched = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "credential_action": "keep",
            "username": "admin",
            "password": "SyntheticNewPass2!",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["trust_lifecycle"]["material"] is True
    assert any("credential" in r for r in body["trust_lifecycle"]["reasons"])

    new = secrets.get_camera_secret(f"camera-{cid}.bin")
    assert new and new.get("password") == "SyntheticNewPass2!"
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, cid)
        assert cam.config_revision != "rev-keep-pwd"
        ev = db.scalar(select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == evid))
        assert ev.revoked is True
        appr = db.scalar(
            select(PilotApprovalRecord)
            .where(PilotApprovalRecord.camera_id == cid, PilotApprovalRecord.kind == "CAMERA_LAB")
            .order_by(PilotApprovalRecord.id.desc())
        )
        assert appr.revoked is True and appr.signature
        assert (
            verify_active_approval(
                db,
                secret_key=app.state.container.settings.secret_key,
                kind="CAMERA_LAB",
                camera_id=cid,
                **pins,
            )
            is None
        )


def test_http_keep_username_change_invalidates(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = _create_cam(client, headers, name="HF5KeepUser", host="192.168.0.222")
    _seed_signed(app, camera_id=cid, rev="rev-keep-user", pins=pins, tag="ku")
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={"credential_action": "keep", "username": "operator2", "password": ""},
    )
    assert r.status_code == 200, r.text
    assert r.json()["trust_lifecycle"]["material"] is True
    secrets = app.state.container.secrets
    stored = secrets.get_camera_secret(f"camera-{cid}.bin")
    assert stored["username"] == "operator2"
    assert stored["password"] == "SyntheticOldPass1!"
    with app.state.container.session_factory() as db:
        assert (
            verify_active_approval(
                db,
                secret_key=app.state.container.settings.secret_key,
                kind="CAMERA_LAB",
                camera_id=cid,
                **pins,
            )
            is None
        )


def test_http_invalid_credential_action_422(app_client):
    client, app = app_client
    headers = _login(client)
    cid = _create_cam(client, headers, name="HF5BadAct", host="192.168.0.223")
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={"credential_action": "explode", "password": "x"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIAL_ACTION"


def test_http_blank_password_keep_and_name_preserve(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = _create_cam(client, headers, name="HF5Safe", host="192.168.0.224")
    _seed_signed(app, camera_id=cid, rev="rev-safe", pins=pins, tag="safe")
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={"name": "HF5Safe Renamed", "credential_action": "keep", "password": ""},
    )
    assert r.status_code == 200
    assert r.json()["trust_lifecycle"]["material"] is False
    with app.state.container.session_factory() as db:
        assert verify_active_approval(
            db, secret_key=app.state.container.settings.secret_key, kind="CAMERA_LAB", camera_id=cid, **pins
        )


def test_http_explicit_replace_and_remove(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = _create_cam(client, headers, name="HF5Rep", host="192.168.0.225")
    _seed_signed(app, camera_id=cid, rev="rev-rep", pins=pins, tag="rep")
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "credential_action": "replace",
            "username": "admin",
            "password": "SyntheticReplace3!",
        },
    )
    assert r.status_code == 200
    assert r.json()["trust_lifecycle"]["material"] is True
    with app.state.container.session_factory() as db:
        assert (
            verify_active_approval(
                db,
                secret_key=app.state.container.settings.secret_key,
                kind="CAMERA_LAB",
                camera_id=cid,
                **pins,
            )
            is None
        )
    # Re-seed and remove
    _seed_signed(app, camera_id=cid, rev="rev-rem", pins=pins, tag="rem")
    r2 = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={"credential_action": "remove"},
    )
    assert r2.status_code == 200
    assert r2.json()["trust_lifecycle"]["material"] is True


def test_auto_validated_http_and_verify_require_ab(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = _create_cam(client, headers, name="HF5AB", host="192.168.0.226")
    now = utc_now()
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, cid)
        cam.config_revision = "rev-ab"
        cam.enabled = True
        cam.mock_mode = False
        binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == cid))
        if binding is None:
            binding = CameraLiveBinding(camera_id=cid)
            db.add(binding)
        binding.config_revision = "rev-ab"
        binding.host = cam.host
        binding.enabled = True
        for kind in ("CAMERA_LAB", "FACE_PILOT"):
            db.add(
                CameraLabRun(
                    run_id=f"run-{kind}-{cid}",
                    nonce=f"n-{kind}-{cid}",
                    kind=kind,
                    camera_id=cid,
                    state="PHYSICAL_VERIFIED",
                    config_revision="rev-ab",
                    provenance="CAMERA_LIVE",
                    model_hash_pin=pins["model_hash_pin"],
                    gallery_revision_pin=pins["gallery_revision_pin"],
                    threshold_id_pin=pins["threshold_id_pin"],
                    started_at=now,
                    expires_at=now + timedelta(hours=7),
                )
            )
            db.add(
                PilotEvidenceRecord(
                    evidence_id=f"ev-{kind}-{cid}",
                    kind=kind,
                    evidence_class=EVIDENCE_PHYSICAL,
                    camera_id=cid,
                    lab_run_id=f"run-{kind}-{cid}",
                    config_revision="rev-ab",
                    provenance="CAMERA_LIVE",
                    labeled_known=2 if kind == "FACE_PILOT" else 0,
                    labeled_unknown=2 if kind == "FACE_PILOT" else 0,
                    decoded_w=640 if kind == "CAMERA_LAB" else None,
                    decoded_h=360 if kind == "CAMERA_LAB" else None,
                    model_hash_pin=pins["model_hash_pin"],
                    gallery_revision_pin=pins["gallery_revision_pin"],
                    threshold_id_pin=pins["threshold_id_pin"],
                    operator="admin",
                    created_at=now,
                    payload_json="{}",
                )
            )
            issue_approval(
                db,
                secret_key=app.state.container.settings.secret_key,
                kind=kind,
                camera_id=cid,
                issued_by="admin",
                evidence_id=f"ev-{kind}-{cid}",
                **pins,
            )
        # Missing AB issuance rejected
        missing = client.post(
            f"/api/v1/cameras/{cid}/quality/approvals",
            headers=headers,
            json={"kind": "AUTO_VALIDATED", "ab_run_id": "no-such-ab"},
        )
        assert missing.status_code == 422

        # Promotable AB
        ab = AbEvaluationRun(
            camera_id=cid,
            run_id=f"ab-ok-{cid}",
            source_mix="LIVE",
            sample_count=4,
            metrics_json="{}",
            blockers_json="[]",
            can_auto_enable=True,
            approval_status="APPROVED",
            evidence_class=EVIDENCE_PHYSICAL,
            config_revision="rev-ab",
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
            created_at=now,
        )
        db.add(ab)
        db.commit()
        assert ab_run_promotable(ab)[0] is True

        issue_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="AUTO_VALIDATED",
            camera_id=cid,
            issued_by="admin",
            ab_run_id=f"ab-ok-{cid}",
            **pins,
        )
        db.commit()
        assert verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="AUTO_VALIDATED",
            camera_id=cid,
            **pins,
        )
        # Reject AB → AUTO_VALIDATED deny
        ab2 = db.scalar(select(AbEvaluationRun).where(AbEvaluationRun.run_id == f"ab-ok-{cid}"))
        ab2.approval_status = "REJECTED"
        ab2.can_auto_enable = False
        db.commit()
        assert (
            verify_active_approval(
                db,
                secret_key=app.state.container.settings.secret_key,
                kind="AUTO_VALIDATED",
                camera_id=cid,
                **pins,
            )
            is None
        )

"""PR16-HF4: camera PATCH material changes + TTL policy + AUTO_VALIDATED deps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
from app.services.evidence_store import (
    EVIDENCE_PHYSICAL,
    KIND_CAMERA_LAB,
    evaluate_physical_sign_eligibility,
)
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


def _seed_signed_physical(app, *, camera_id: int, rev: str, pins: dict[str, str]):
    now = utc_now()
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, camera_id)
        cam.config_revision = rev
        cam.mock_mode = False
        cam.enabled = True
        cam.archived = False
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
                run_id=f"run-hf4-{camera_id}",
                nonce=f"nonce-hf4-{camera_id}",
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
                fps_measured=15.0,
                started_at=now,
                expires_at=now + timedelta(hours=7),
                verified_at=now,
                owner_reviewed_by="admin",
                owner_reviewed_at=now,
            )
        )
        db.add(
            PilotEvidenceRecord(
                evidence_id=f"ev-hf4-{camera_id}",
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=camera_id,
                lab_run_id=f"run-hf4-{camera_id}",
                config_revision=rev,
                provenance="CAMERA_LIVE",
                decoded_w=640,
                decoded_h=360,
                fps_measured=15.0,
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
            evidence_id=f"ev-hf4-{camera_id}",
            **pins,
        )
        db.commit()


def test_http_patch_material_host_invalidates_gate(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF4Mat",
            "host": "192.168.0.211",
            "rtsp_url_override": "rtsp://192.168.0.211:554/ch1/main",
            "mock_mode": False,
            "enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    _seed_signed_physical(app, camera_id=cid, rev="rev-hf4-a", pins=pins)

    with app.state.container.session_factory() as db:
        assert evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
        ).eligible
        assert verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            **pins,
        )

    patched = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={
            "host": "192.168.0.250",
            "rtsp_url_override": "rtsp://192.168.0.250:554/ch1/main",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body.get("trust_lifecycle", {}).get("material") is True
    assert "host" in (body.get("trust_lifecycle", {}).get("reasons") or [])

    with app.state.container.session_factory() as db:
        elig = evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
        )
        assert elig.eligible is False
        active = verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            **pins,
        )
        assert active is None
        cam = db.get(CameraDevice, cid)
        assert cam.config_revision != "rev-hf4-a"
        ev = db.scalar(
            select(PilotEvidenceRecord).where(
                PilotEvidenceRecord.evidence_id == f"ev-hf4-{cid}"
            )
        )
        assert ev.revoked is True
        appr = db.scalar(
            select(PilotApprovalRecord).where(PilotApprovalRecord.camera_id == cid)
        )
        assert appr is not None and appr.revoked is True and appr.signature


def test_http_patch_name_only_preserves_gate(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF4Name",
            "host": "192.168.0.212",
            "mock_mode": False,
            "enabled": True,
        },
    ).json()["id"]
    _seed_signed_physical(app, camera_id=cid, rev="rev-name", pins=pins)
    r = client.patch(
        f"/api/v1/cameras/{cid}",
        headers=headers,
        json={"name": "HF4Name Renamed"},
    )
    assert r.status_code == 200
    assert r.json().get("trust_lifecycle", {}).get("material") is False
    with app.state.container.session_factory() as db:
        assert evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
        ).eligible
        assert verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            **pins,
        )


def test_http_disable_closes_gate_without_revoke_evidence(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "HF4Dis", "host": "192.168.0.213", "mock_mode": False, "enabled": True},
    ).json()["id"]
    _seed_signed_physical(app, camera_id=cid, rev="rev-dis", pins=pins)
    r = client.patch(f"/api/v1/cameras/{cid}", headers=headers, json={"enabled": False})
    assert r.status_code == 200
    assert r.json().get("trust_lifecycle", {}).get("material") is False
    with app.state.container.session_factory() as db:
        elig = evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
        )
        assert elig.eligible is False
        assert elig.code == "CAMERA_DISABLED"
        ev = db.scalar(
            select(PilotEvidenceRecord).where(
                PilotEvidenceRecord.evidence_id == f"ev-hf4-{cid}"
            )
        )
        assert ev.revoked is False  # no forced re-lab
        assert verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            **pins,
        ) is None
    # Resume — evidence still valid under same revision
    r2 = client.patch(f"/api/v1/cameras/{cid}", headers=headers, json={"enabled": True})
    assert r2.status_code == 200
    with app.state.container.session_factory() as db:
        assert evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
        ).eligible


def test_physical_challenge_ttl_does_not_kill_hmac(app_client):
    """P1-C: after PHYSICAL_VERIFIED, lab challenge TTL expiry must not deny HMAC."""
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "HF4TTL", "host": "192.168.0.214", "mock_mode": False, "enabled": True},
    ).json()["id"]
    _seed_signed_physical(app, camera_id=cid, rev="rev-ttl", pins=pins)
    clock = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    with app.state.container.session_factory() as db:
        run = db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == f"run-hf4-{cid}"))
        # Challenge window already over; PHYSICAL promotion already done
        run.expires_at = clock - timedelta(hours=1)
        run.verified_at = clock - timedelta(hours=2)
        db.commit()
        elig = evaluate_physical_sign_eligibility(
            db,
            kind="CAMERA_LAB",
            camera_id=cid,
            evidence_id=f"ev-hf4-{cid}",
            pins=pins,
            clock=clock,
        )
        assert elig.eligible is True, elig
        active = verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            clock=clock,
            **pins,
        )
        assert active is not None and active.valid


def test_auto_validated_invalid_when_camera_lab_revoked(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cid = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "HF4AV", "host": "192.168.0.215", "mock_mode": False, "enabled": True},
    ).json()["id"]
    _seed_signed_physical(app, camera_id=cid, rev="rev-av", pins=pins)
    # Minimal FACE_PILOT backing for dependency check
    now = utc_now()
    with app.state.container.session_factory() as db:
        db.add(
            CameraLabRun(
                run_id=f"run-face-{cid}",
                nonce=f"nonce-face-{cid}",
                kind="FACE_PILOT",
                camera_id=cid,
                state="PHYSICAL_VERIFIED",
                revoked=False,
                config_revision="rev-av",
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
                evidence_id=f"ev-face-{cid}",
                kind="FACE_PILOT",
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=cid,
                lab_run_id=f"run-face-{cid}",
                config_revision="rev-av",
                provenance="CAMERA_LIVE",
                labeled_known=2,
                labeled_unknown=2,
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
            kind="FACE_PILOT",
            camera_id=cid,
            issued_by="admin",
            evidence_id=f"ev-face-{cid}",
            **pins,
        )
        db.add(
            AbEvaluationRun(
                camera_id=cid,
                run_id=f"ab-hf4-{cid}",
                source_mix="LIVE",
                sample_count=4,
                metrics_json="{}",
                blockers_json="[]",
                can_auto_enable=True,
                approval_status="APPROVED",
                evidence_class=EVIDENCE_PHYSICAL,
                config_revision="rev-av",
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                created_at=now,
            )
        )
        issue_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="AUTO_VALIDATED",
            camera_id=cid,
            issued_by="admin",
            ab_run_id=f"ab-hf4-{cid}",
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
        # Revoke CAMERA_LAB evidence → AUTO_VALIDATED must fail
        from app.services.evidence_store import revoke_physical_evidence_for_camera

        revoke_physical_evidence_for_camera(db, camera_id=cid, reason="TEST_AV_DEP")
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

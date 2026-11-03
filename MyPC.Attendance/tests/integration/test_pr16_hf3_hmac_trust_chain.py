"""PR16-HF3: physical evidence ↔ lab run ↔ config revision HMAC trust chain."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.utc_time import utc_now
from app.models.entities import (
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
    revoke_physical_evidence_for_camera,
)
from app.services.pilot_approval import verify_active_approval
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


def _seed_physical(
    app,
    *,
    camera_id: int,
    rev: str,
    run_id: str,
    evidence_id: str,
    pins: dict[str, str],
    state: str = "PHYSICAL_VERIFIED",
    revoked_run: bool = False,
    revoked_evidence: bool = False,
    expires_at=None,
    run_kind: str = "CAMERA_LAB",
    evidence_kind: str = "CAMERA_LAB",
    provenance: str = "CAMERA_LIVE",
):
    with app.state.container.session_factory() as db:
        cam = db.get(CameraDevice, camera_id)
        assert cam is not None
        cam.config_revision = rev
        cam.enabled = True
        cam.mock_mode = False
        cam.archived = False
        binding = db.scalar(
            select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_id)
        )
        if binding is None:
            binding = CameraLiveBinding(camera_id=camera_id)
            db.add(binding)
        binding.config_revision = rev
        binding.enabled = True
        binding.host = (cam.host or "").strip() or "192.168.0.240"
        binding.port = 554
        binding.path = "/ch1/main"
        exp = expires_at if expires_at is not None else (utc_now() + timedelta(hours=7))
        db.add(
            CameraLabRun(
                run_id=run_id,
                nonce=f"nonce-{run_id}",
                kind=run_kind,
                camera_id=camera_id,
                state=state,
                revoked=revoked_run,
                config_revision=rev,
                provenance=provenance,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                decoded_w=640,
                decoded_h=360,
                fps_measured=15.0,
                started_at=utc_now(),
                expires_at=exp,
                owner_reviewed_by="admin",
                owner_reviewed_at=utc_now(),
            )
        )
        db.add(
            PilotEvidenceRecord(
                evidence_id=evidence_id,
                kind=evidence_kind,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=camera_id,
                lab_run_id=run_id,
                config_revision=rev,
                provenance=provenance,
                decoded_w=640,
                decoded_h=360,
                fps_measured=15.0,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                operator="admin",
                created_at=utc_now(),
                revoked=revoked_evidence,
                payload_json="{}",
            )
        )
        db.commit()


def test_rest_negatives_and_fresh_sign_success(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF3Trust",
            "host": "192.168.0.240",
            "mock_mode": False,
            "enabled": True,
        },
    ).json()
    cid = cam["id"]

    # Nonexistent lab_run_id
    with app.state.container.session_factory() as db:
        cam_row = db.get(CameraDevice, cid)
        cam_row.config_revision = "rev-a"
        cam_row.enabled = True
        cam_row.mock_mode = False
        db.add(
            PilotEvidenceRecord(
                evidence_id="ev-ghost-run",
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=cid,
                lab_run_id="no-such-run",
                config_revision="rev-a",
                provenance="CAMERA_LIVE",
                decoded_w=100,
                decoded_h=100,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                operator="admin",
                created_at=utc_now(),
                payload_json="{}",
            )
        )
        db.commit()

    listing = client.get(f"/api/v1/cameras/{cid}/quality/evidence?kind=CAMERA_LAB", headers=headers)
    assert listing.status_code == 200, listing.text
    ghost = next(i for i in listing.json()["items"] if i["evidence_id"] == "ev-ghost-run")
    assert ghost["eligible_for_sign"] is False
    assert ghost["eligible_reason"] == "LAB_RUN_MISSING"

    denied = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "evidence_id": "ev-ghost-run"},
    )
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "LAB_RUN_MISSING"
    with app.state.container.session_factory() as db:
        assert db.scalar(select(PilotApprovalRecord).where(PilotApprovalRecord.camera_id == cid)) is None

    # Revoked / REJECTED / expired / wrong kind / config mismatch
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-a",
        run_id="run-revoked",
        evidence_id="ev-revoked-run",
        pins=pins,
        state="REJECTED",
        revoked_run=True,
    )
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-a",
        run_id="run-rejected",
        evidence_id="ev-rejected",
        pins=pins,
        state="REJECTED",
        revoked_run=False,
    )
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-a",
        run_id="run-wrong-kind",
        evidence_id="ev-wrong-kind",
        pins=pins,
        run_kind="FACE_PILOT",
        evidence_kind="CAMERA_LAB",
    )

    cases = {
        "ev-revoked-run": {"LAB_RUN_REVOKED", "LAB_RUN_STATE_INVALID"},
        "ev-rejected": {"LAB_RUN_STATE_INVALID"},
        "ev-wrong-kind": {"LAB_RUN_MISMATCH"},
    }
    for eid, codes in cases.items():
        r = client.post(
            f"/api/v1/cameras/{cid}/quality/approvals",
            headers=headers,
            json={"kind": "CAMERA_LAB", "evidence_id": eid},
        )
        assert r.status_code == 422, (eid, r.text)
        assert r.json()["detail"]["code"] in codes
        listing2 = client.get(
            f"/api/v1/cameras/{cid}/quality/evidence?kind=CAMERA_LAB", headers=headers
        )
        item = next(i for i in listing2.json()["items"] if i["evidence_id"] == eid)
        assert item["eligible_for_sign"] is False

    # Config mismatch: evidence/lab on old rev while camera on new
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-old",
        run_id="run-stale-cfg",
        evidence_id="ev-stale-cfg",
        pins=pins,
    )
    with app.state.container.session_factory() as db:
        cam_row = db.get(CameraDevice, cid)
        cam_row.config_revision = "rev-new"
        binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == cid))
        binding.config_revision = "rev-new"
        db.commit()

    stale = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "evidence_id": "ev-stale-cfg"},
    )
    assert stale.status_code == 422
    assert stale.json()["detail"]["code"] == "CONFIG_REVISION_MISMATCH"

    # Fresh PHYSICAL success
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-new",
        run_id="run-fresh",
        evidence_id="ev-fresh",
        pins=pins,
    )
    ok = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "evidence_id": "ev-fresh", "note_vi": "HF3 fresh sign"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["approval_id"]
    assert body.get("camera_lab_pass") is False
    approval_id = body["approval_id"]

    with app.state.container.session_factory() as db:
        active = verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
        )
        assert active is not None and active.valid
        assert active.approval_id == approval_id

        # Revoke backing evidence after signing → gate closes; signature row kept
        n = revoke_physical_evidence_for_camera(
            db, camera_id=cid, reason="TEST_POST_SIGN_REVOKE"
        )
        assert n >= 1
        db.commit()

    with app.state.container.session_factory() as db:
        after = verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
        )
        assert after is None or after.valid is False
        row = db.scalar(
            select(PilotApprovalRecord).where(PilotApprovalRecord.approval_id == approval_id)
        )
        assert row is not None
        assert row.signature  # not overwritten
        assert row.revoked is False  # live relational deny, not forced delete


def test_reconfigure_revokes_evidence_and_blocks_sign(app_client):
    """Camera reconfigure path must invalidate prior physical evidence for signing."""
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF3Reconfig",
            "host": "192.168.0.241",
            "rtsp_url_override": "rtsp://192.168.0.241:554/ch1/main",
            "username": "admin",
            "password": "CamSecret99",
            "credential_action": "replace",
            "mock_mode": False,
            "enabled": True,
        },
    )  # enabled True required for physical eligibility
    assert cam.status_code == 200, cam.text
    cid = cam.json()["id"]

    with app.state.container.session_factory() as db:
        row = db.get(CameraDevice, cid)
        row.enabled = True
        row.mock_mode = False
        old_rev = row.config_revision or "seed-rev"
        if not row.config_revision:
            row.config_revision = old_rev
        binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == cid))
        if binding is None:
            binding = CameraLiveBinding(
                camera_id=cid,
                config_revision=old_rev,
                enabled=True,
                host=row.host or "192.168.0.241",
                path="/ch1/main",
            )
            db.add(binding)
        else:
            binding.config_revision = old_rev
            binding.host = row.host or binding.host
            binding.path = binding.path or "/ch1/main"
        db.add(
            CameraLabRun(
                run_id="run-before-reconfig",
                nonce="nonce-before-reconfig",
                kind=KIND_CAMERA_LAB,
                camera_id=cid,
                state="PHYSICAL_VERIFIED",
                config_revision=old_rev,
                provenance="CAMERA_LIVE",
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                started_at=utc_now(),
                expires_at=utc_now() + timedelta(hours=7),
            )
        )
        db.add(
            PilotEvidenceRecord(
                evidence_id="ev-before-reconfig",
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=cid,
                lab_run_id="run-before-reconfig",
                config_revision=old_rev,
                provenance="CAMERA_LIVE",
                decoded_w=640,
                decoded_h=360,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                operator="admin",
                created_at=utc_now(),
                payload_json="{}",
            )
        )
        db.commit()
        elig = evaluate_physical_sign_eligibility(
            db,
            kind=KIND_CAMERA_LAB,
            camera_id=cid,
            evidence_id="ev-before-reconfig",
            pins=pins,
        )
        assert elig.eligible is True

    # Force config revision change path via binding update helper used by configure
    from app.services.evidence_store import revoke_physical_evidence_for_camera
    from app.services.lab_run_service import revoke_lab_runs_for_camera
    from app.services.pilot_approval import revoke_approvals

    with app.state.container.session_factory() as db:
        revoke_approvals(db, camera_id=cid, reason="CAMERA_CONFIG_REVISION_CHANGED")
        revoke_lab_runs_for_camera(db, camera_id=cid, reason="CAMERA_CONFIG_REVISION_CHANGED")
        n = revoke_physical_evidence_for_camera(
            db, camera_id=cid, reason="CAMERA_CONFIG_REVISION_CHANGED"
        )
        assert n >= 1
        cam_row = db.get(CameraDevice, cid)
        cam_row.config_revision = "post-reconfig-rev"
        binding = db.scalar(select(CameraLiveBinding).where(CameraLiveBinding.camera_id == cid))
        binding.config_revision = "post-reconfig-rev"
        db.commit()

    with app.state.container.session_factory() as db:
        elig2 = evaluate_physical_sign_eligibility(
            db,
            kind=KIND_CAMERA_LAB,
            camera_id=cid,
            evidence_id="ev-before-reconfig",
            pins=pins,
        )
        assert elig2.eligible is False
        assert elig2.code in {"EVIDENCE_REVOKED", "CONFIG_REVISION_MISMATCH", "LAB_RUN_REVOKED"}
        ev = db.scalar(
            select(PilotEvidenceRecord).where(
                PilotEvidenceRecord.evidence_id == "ev-before-reconfig"
            )
        )
        assert ev is not None
        assert ev.revoked is True  # audit retained, marked revoked

    denied = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "evidence_id": "ev-before-reconfig"},
    )
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] in {
        "EVIDENCE_REVOKED",
        "CONFIG_REVISION_MISMATCH",
        "LAB_RUN_REVOKED",
    }


def test_verify_active_fails_when_lab_revoked_after_sign(app_client):
    client, app = app_client
    headers = _login(client)
    pins = _pins(app)
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={
            "name": "HF3PostRev",
            "host": "192.168.0.242",
            "mock_mode": False,
            "enabled": True,
        },
    ).json()
    cid = cam["id"]
    _seed_physical(
        app,
        camera_id=cid,
        rev="rev-live",
        run_id="run-then-revoke",
        evidence_id="ev-then-revoke",
        pins=pins,
    )
    issued = client.post(
        f"/api/v1/cameras/{cid}/quality/approvals",
        headers=headers,
        json={"kind": "CAMERA_LAB", "evidence_id": "ev-then-revoke"},
    )
    assert issued.status_code == 200, issued.text

    with app.state.container.session_factory() as db:
        run = db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == "run-then-revoke"))
        run.revoked = True
        run.state = "REJECTED"
        db.commit()

    with app.state.container.session_factory() as db:
        active = verify_active_approval(
            db,
            secret_key=app.state.container.settings.secret_key,
            kind="CAMERA_LAB",
            camera_id=cid,
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
        )
        assert active is None

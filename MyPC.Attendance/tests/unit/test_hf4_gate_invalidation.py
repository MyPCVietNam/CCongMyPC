"""Independent PR16-HF3 regressions. THESE TESTS ARE EXPECTED TO FAIL ON HF3.

Copy under MyPC.Attendance/tests/unit/ and run against the repository's pinned
Python environment. All data are synthetic in an in-memory SQLite database.
No camera, secrets, DataDir, network, or GitHub access is required.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.cameras import CameraUpdate, update_camera
from app.core.database import Base
from app.core.utc_time import utc_now
from app.models.entities import (
    CameraDevice, CameraLabRun, CameraLiveBinding, PilotEvidenceRecord,
)
from app.services.evidence_store import evaluate_physical_sign_eligibility
from app.services.pilot_approval import issue_approval, verify_active_approval

PINS = {
    "model_hash_pin": "synthetic-model-pin",
    "gallery_revision_pin": "synthetic-gallery-revision",
    "threshold_id_pin": "synthetic-threshold-pin",
}
KEY = "synthetic-not-for-production-approval-key"


class NoSecrets:
    def has_secret(self, _ref: str) -> bool:
        return False


@pytest.fixture
def physical_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as db:
        cam = CameraDevice(
            name="Audit synthetic camera", host="192.168.0.211",
            rtsp_url_override="rtsp://192.168.0.211:554/ch1/main",
            created_at=now, archived=False, enabled=True, mock_mode=False,
            config_revision="revision-A",
        )
        db.add(cam)
        db.flush()
        db.add(CameraLiveBinding(
            camera_id=cam.id, config_revision="revision-A", enabled=True,
            host="192.168.0.211", port=554, path="/ch1/main",
        ))
        db.add(CameraLabRun(
            run_id="run-synthetic", nonce="nonce-synthetic",
            kind="CAMERA_LAB", camera_id=cam.id, state="PHYSICAL_VERIFIED",
            revoked=False, config_revision="revision-A", provenance="CAMERA_LIVE",
            decoded_w=2880, decoded_h=1620, fps_measured=18.0,
            owner_reviewed_by="synthetic-owner", owner_reviewed_at=now,
            started_at=now, expires_at=now + timedelta(hours=7),
            **PINS,
        ))
        db.add(PilotEvidenceRecord(
            evidence_id="evidence-synthetic", kind="CAMERA_LAB",
            evidence_class="PHYSICAL_VERIFIED", camera_id=cam.id,
            lab_run_id="run-synthetic", config_revision="revision-A",
            provenance="CAMERA_LIVE", decoded_w=2880, decoded_h=1620,
            fps_measured=18.0, operator="synthetic-owner", created_at=now,
            payload_json="{}", **PINS,
        ))
        db.flush()
        issue_approval(
            db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cam.id,
            issued_by="synthetic-owner", evidence_id="evidence-synthetic", **PINS,
        )
        db.commit()
        yield db, cam.id
    engine.dispose()


def active(db: Session, cid: int) -> bool:
    v = verify_active_approval(
        db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cid, **PINS,
    )
    return bool(v is not None and v.valid)


def eligibility(db: Session, cid: int) -> bool:
    return evaluate_physical_sign_eligibility(
        db, kind="CAMERA_LAB", camera_id=cid,
        evidence_id="evidence-synthetic", pins=PINS,
    ).eligible


def change(db: Session, cid: int, body: CameraUpdate) -> None:
    update_camera(
        cid, body, db,
        SimpleNamespace(camera_registry=None, secrets=NoSecrets()),
        SimpleNamespace(username="synthetic-owner"),
    )
    db.commit()


def test_patch_changed_rtsp_host_revokes_or_invalidates_old_hmac(physical_db):
    db, cid = physical_db
    assert active(db, cid)
    change(db, cid, CameraUpdate(
        host="192.168.0.250", rtsp_url_override="rtsp://192.168.0.250:554/ch1/main"
    ))
    assert not eligibility(db, cid), "Old PHYSICAL evidence remained sign-eligible after source change"
    assert not active(db, cid), "Old signed HMAC remained active after source change"


def test_patch_mock_or_disable_cannot_leave_operational_gate_open(physical_db):
    db, cid = physical_db
    assert active(db, cid)
    change(db, cid, CameraUpdate(mock_mode=True, enabled=False))
    assert not eligibility(db, cid), "MOCK/disabled camera remains eligible for physical signing"
    assert not active(db, cid), "MOCK/disabled camera retained active physical gate"


def test_empty_run_and_evidence_provenance_must_fail_closed(physical_db):
    db, cid = physical_db
    run = db.query(CameraLabRun).filter_by(run_id="run-synthetic").one()
    evidence = db.query(PilotEvidenceRecord).filter_by(evidence_id="evidence-synthetic").one()
    run.provenance = ""
    evidence.provenance = ""
    db.flush()
    assert not eligibility(db, cid), "Missing CAMERA_LIVE provenance was accepted"


def test_null_lab_run_expiry_must_require_explicit_policy(physical_db):
    db, cid = physical_db
    run = db.query(CameraLabRun).filter_by(run_id="run-synthetic").one()
    run.expires_at = None
    db.flush()
    assert not eligibility(db, cid), "NULL lab run expiration was accepted without explicit policy"

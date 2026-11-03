"""PR16-HF3 regression: revoked/outdated lab run must not authorize HMAC.

Adapted from independent audit repro (expected FAIL on PR16-HF2; PASS here).
Uses only an in-memory SQLite DB. No network, credentials, or live camera.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.utc_time import utc_now
from app.models.entities import CameraDevice, CameraLabRun, PilotEvidenceRecord
from app.services.evidence_store import (
    list_physical_evidence_for_camera,
    require_physical_evidence,
)


def test_revoked_previous_revision_run_cannot_authorize_hmac():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    pins = {
        "model_hash_pin": "synthetic-model-pin",
        "gallery_revision_pin": "synthetic-gallery-pin",
        "threshold_id_pin": "synthetic-threshold-pin",
    }
    with Session(engine) as db:
        cam = CameraDevice(
            name="Synthetic audit camera",
            host="192.0.2.10",
            mock_mode=False,
            enabled=True,
            config_revision="new-config",
            created_at=utc_now(),
        )
        db.add(cam)
        db.flush()
        db.add(
            CameraLabRun(
                run_id="revoked-old-run",
                nonce="synthetic-nonce",
                kind="CAMERA_LAB",
                camera_id=cam.id,
                state="REJECTED",
                revoked=True,
                config_revision="old-config",
                started_at=utc_now(),
            )
        )
        evidence = PilotEvidenceRecord(
            evidence_id="old-physical-evidence",
            kind="CAMERA_LAB",
            evidence_class="PHYSICAL_VERIFIED",
            camera_id=cam.id,
            lab_run_id="revoked-old-run",
            config_revision="old-config",
            provenance="CAMERA_LIVE",
            decoded_w=2880,
            decoded_h=1620,
            fps_measured=19.7,
            model_hash_pin=pins["model_hash_pin"],
            gallery_revision_pin=pins["gallery_revision_pin"],
            threshold_id_pin=pins["threshold_id_pin"],
            operator="synthetic",
            created_at=utc_now(),
            revoked=False,
        )
        db.add(evidence)
        db.flush()
        listing = list_physical_evidence_for_camera(
            db, camera_id=cam.id, kind="CAMERA_LAB", pins=pins
        )
        approval_check = require_physical_evidence(
            db,
            kind="CAMERA_LAB",
            camera_id=cam.id,
            evidence_id=evidence.evidence_id,
            pins=pins,
        )
        assert listing, "evidence row still listed for audit"
        assert not listing[0]["eligible_for_sign"], (
            "Revoked/outdated lab run must not remain eligible for HMAC signing"
        )
        assert listing[0]["eligible_reason"] in {
            "LAB_RUN_REVOKED",
            "CONFIG_REVISION_MISMATCH",
            "LAB_RUN_STATE_INVALID",
        }
        assert not approval_check.valid, (
            "Backend must reject evidence from revoked/previous config lab run"
        )
        assert approval_check.code in {
            "LAB_RUN_REVOKED",
            "CONFIG_REVISION_MISMATCH",
            "LAB_RUN_STATE_INVALID",
        }


def test_nonexistent_lab_run_id_not_eligible():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    pins = {
        "model_hash_pin": "m",
        "gallery_revision_pin": "g",
        "threshold_id_pin": "t",
    }
    with Session(engine) as db:
        cam = CameraDevice(
            name="MissingRunCam",
            host="192.0.2.11",
            mock_mode=False,
            enabled=True,
            config_revision="cfg-now",
            created_at=utc_now(),
        )
        db.add(cam)
        db.flush()
        evidence = PilotEvidenceRecord(
            evidence_id="ev-missing-run",
            kind="CAMERA_LAB",
            evidence_class="PHYSICAL_VERIFIED",
            camera_id=cam.id,
            lab_run_id="does-not-exist",
            config_revision="cfg-now",
            provenance="CAMERA_LIVE",
            decoded_w=100,
            decoded_h=100,
            fps_measured=10.0,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            operator="synthetic",
            created_at=utc_now(),
            revoked=False,
        )
        db.add(evidence)
        db.flush()
        listing = list_physical_evidence_for_camera(
            db, camera_id=cam.id, kind="CAMERA_LAB", pins=pins
        )
        check = require_physical_evidence(
            db,
            kind="CAMERA_LAB",
            camera_id=cam.id,
            evidence_id=evidence.evidence_id,
            pins=pins,
        )
        assert listing[0]["eligible_for_sign"] is False
        assert listing[0]["eligible_reason"] == "LAB_RUN_MISSING"
        assert check.valid is False
        assert check.code == "LAB_RUN_MISSING"

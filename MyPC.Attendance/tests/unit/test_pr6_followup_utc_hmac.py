"""PR6 follow-up P0: SQLite UTC + stable HMAC canonical approvals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.core.utc_time import (
    AmbiguousTimestampError,
    canonical_utc_z,
    parse_canonical_utc_z,
    to_utc_aware,
)
from app.models.entities import CameraDevice, CameraLabRun, PilotApprovalRecord, PilotEvidenceRecord
from app.services.pilot_approval import issue_approval, revoke_approvals, verify_active_approval

SECRET = "unit-test-csprng-secret-key-not-for-production-use-9f3a"


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'apr.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as s:
        yield s
        s.rollback()


def _seed_physical_backing(
    db: Session,
    *,
    camera_id: int,
    evidence_id: str,
    kind: str = "CAMERA_LAB",
    rev: str = "rev-hmac",
    pins: dict[str, str] | None = None,
) -> None:
    """PR16-HF3: verify_active_approval re-checks live evidence/lab run."""
    pins = pins or {
        "model_hash_pin": "m1",
        "gallery_revision_pin": "g1",
        "threshold_id_pin": "t1",
    }
    cam = db.get(CameraDevice, camera_id)
    if cam is None:
        cam = CameraDevice(
            id=camera_id,
            name=f"Cam{camera_id}",
            host="192.0.2.50",
            mock_mode=False,
            enabled=True,
            config_revision=rev,
            created_at=datetime.now(timezone.utc),
        )
        db.add(cam)
        db.flush()
    else:
        cam.config_revision = rev
    run_id = f"lab-{evidence_id}"
    if db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == run_id)) is None:
        db.add(
            CameraLabRun(
                run_id=run_id,
                nonce=f"nonce-{evidence_id}",
                kind=kind,
                camera_id=camera_id,
                state="PHYSICAL_VERIFIED",
                revoked=False,
                config_revision=rev,
                provenance="CAMERA_LIVE",
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                started_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=7),
            )
        )
    if (
        db.scalar(select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == evidence_id))
        is None
    ):
        db.add(
            PilotEvidenceRecord(
                evidence_id=evidence_id,
                kind=kind,
                evidence_class="PHYSICAL_VERIFIED",
                camera_id=camera_id,
                lab_run_id=run_id,
                config_revision=rev,
                provenance="CAMERA_LIVE",
                decoded_w=160,
                decoded_h=120,
                model_hash_pin=pins["model_hash_pin"],
                gallery_revision_pin=pins["gallery_revision_pin"],
                threshold_id_pin=pins["threshold_id_pin"],
                labeled_known=1 if kind == "FACE_PILOT" else 0,
                labeled_unknown=1 if kind == "FACE_PILOT" else 0,
                operator="admin",
                created_at=datetime.now(timezone.utc),
                payload_json="{}",
            )
        )
    db.flush()


def test_canonical_zulu_stable_across_naive_rehydrate():
    aware = datetime(2026, 11, 2, 3, 15, 0, 123, tzinfo=timezone.utc)
    z1 = canonical_utc_z(aware)
    naive = aware.replace(tzinfo=None)
    z2 = canonical_utc_z(naive)
    assert z1 == z2
    assert z1.endswith("Z")
    assert parse_canonical_utc_z(z1) == aware.replace(microsecond=123)


def test_ambiguous_timestamp_rejected():
    with pytest.raises(AmbiguousTimestampError):
        parse_canonical_utc_z("2026-11-02T03:15:00+00:00")
    with pytest.raises(AmbiguousTimestampError):
        parse_canonical_utc_z("not-a-time")


def test_issue_commit_reopen_verify_hmac(db_session: Session, tmp_path):
    clock = datetime(2026, 11, 2, 4, 0, 0, tzinfo=timezone.utc)
    _seed_physical_backing(
        db_session,
        camera_id=7,
        evidence_id="ev-test-1",
        pins={
            "model_hash_pin": "m1",
            "gallery_revision_pin": "g1",
            "threshold_id_pin": "t1",
        },
    )
    row = issue_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=7,
        issued_by="admin",
        model_hash_pin="m1",
        gallery_revision_pin="g1",
        threshold_id_pin="t1",
        evidence_id="ev-test-1",
        clock=clock,
    )
    db_session.commit()
    approval_id = row.approval_id
    payload = row.payload_json

    # New session (SQLite rehydration)
    engine = create_engine(f"sqlite:///{tmp_path / 'apr.sqlite3'}")
    factory = sessionmaker(bind=engine)
    with factory() as s2:
        loaded = s2.scalar(
            select(PilotApprovalRecord).where(PilotApprovalRecord.approval_id == approval_id)
        )
        assert loaded is not None
        # expires_at may be naive after SQLite
        assert loaded.expires_at is not None
        assert to_utc_aware(loaded.expires_at) is not None
        assert loaded.payload_json == payload
        view = verify_active_approval(
            s2,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=7,
            model_hash_pin="m1",
            gallery_revision_pin="g1",
            threshold_id_pin="t1",
            clock=clock + timedelta(hours=1),
        )
        assert view is not None and view.valid
        assert view.approval_id == approval_id


def test_expiry_exact_utc_boundary(db_session: Session):
    clock = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)
    _seed_physical_backing(
        db_session,
        camera_id=1,
        evidence_id="ev-test-1",
        pins={
            "model_hash_pin": "m",
            "gallery_revision_pin": "g",
            "threshold_id_pin": "t",
        },
    )
    row = issue_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=1,
        issued_by="admin",
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        evidence_id="ev-test-1",
        ttl_hours=1,
        clock=clock,
    )
    db_session.commit()
    # Exactly at expiry → rejected
    view = verify_active_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=1,
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        clock=clock + timedelta(hours=1),
    )
    assert view is None
    # One microsecond before → valid
    view2 = verify_active_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=1,
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        clock=to_utc_aware(row.expires_at) - timedelta(microseconds=1),  # type: ignore[operator]
    )
    assert view2 is not None and view2.valid


def test_revoke_and_tamper_fail_closed(db_session: Session):
    clock = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    row = issue_approval(
        db_session,
        secret_key=SECRET,
        kind="FACE_PILOT",
        camera_id=3,
        issued_by="admin",
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        evidence_id="ev-test-1",
        clock=clock,
    )
    db_session.commit()
    revoke_approvals(db_session, kind="FACE_PILOT", camera_id=3, reason="TEST")
    db_session.commit()
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="FACE_PILOT",
            camera_id=3,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=clock,
        )
        is None
    )

    row2 = issue_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=3,
        issued_by="admin",
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        evidence_id="ev-test-1",
        clock=clock,
    )
    db_session.commit()
    # Tamper payload_json → HMAC fails
    row2.payload_json = row2.payload_json.replace('"camera_id":3', '"camera_id":99')
    db_session.commit()
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=3,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=clock,
        )
        is None
    )


def test_missing_pins_fail_closed(db_session: Session):
    view = verify_active_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=1,
        require_pins=True,
    )
    assert view is not None
    assert view.valid is False
    assert view.code == "DENIED_MISSING_PINS"


def test_wrong_key_rotation_fail_closed(db_session: Session):
    clock = datetime(2026, 11, 2, 8, 0, 0, tzinfo=timezone.utc)
    issue_approval(
        db_session,
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=2,
        issued_by="admin",
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        evidence_id="ev-test-1",
        clock=clock,
    )
    db_session.commit()
    rotated = "rotated-test-csprng-secret-key-not-for-production-bbbbbbbb"
    assert (
        verify_active_approval(
            db_session,
            secret_key=rotated,
            kind="CAMERA_LAB",
            camera_id=2,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=clock,
        )
        is None
    )


def test_auto_validated_requires_ab_run_id(db_session: Session):
    with pytest.raises(ValueError):
        issue_approval(
            db_session,
            secret_key=SECRET,
            kind="AUTO_VALIDATED",
            camera_id=1,
            issued_by="admin",
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            ab_run_id="",
        )

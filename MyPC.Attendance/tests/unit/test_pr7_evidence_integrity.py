"""PR7: HMAC row/payload integrity, gallery content pin, pipeline pins."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.entities import PilotApprovalRecord
from app.services.gallery_loader import load_active_gallery
from app.services.pilot_approval import issue_approval, verify_active_approval
from app.services.server_pins import model_hash_from_pipeline, threshold_id_from_pipeline


SECRET = "unit-test-csprng-secret-key-not-for-production-use-9f3a"


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pr7.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as s:
        yield s
        s.rollback()


def _issue(db, **kw):
    base = dict(
        secret_key=SECRET,
        kind="CAMERA_LAB",
        camera_id=1,
        issued_by="admin",
        model_hash_pin="m",
        gallery_revision_pin="g",
        threshold_id_pin="t",
        evidence_id="ev-1",
        clock=datetime(2026, 11, 2, 8, 0, 0, tzinfo=timezone.utc),
    )
    base.update(kw)
    return issue_approval(db, **base)


def test_tamper_kind_rejected(db_session: Session):
    row = _issue(db_session)
    db_session.commit()
    row.kind = "FACE_PILOT"
    db_session.commit()
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="FACE_PILOT",
            camera_id=1,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc),
        )
        is None
    )
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=1,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc),
        )
        is None
    )


def test_tamper_approval_id_rejected(db_session: Session):
    row = _issue(db_session)
    db_session.commit()
    row.approval_id = "forged-id"
    db_session.commit()
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=1,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc),
        )
        is None
    )


def test_tamper_expires_at_rejected(db_session: Session):
    row = _issue(db_session)
    db_session.commit()
    row.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    db_session.commit()
    assert (
        verify_active_approval(
            db_session,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=1,
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            clock=datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc),
        )
        is None
    )


def test_camera_lab_requires_evidence_id(db_session: Session):
    with pytest.raises(ValueError):
        issue_approval(
            db_session,
            secret_key=SECRET,
            kind="CAMERA_LAB",
            camera_id=1,
            issued_by="admin",
            model_hash_pin="m",
            gallery_revision_pin="g",
            threshold_id_pin="t",
            evidence_id="",
        )


class _Pipe:
    def __init__(self, det_h="D1", emb_h="E1", thr=0.45, margin=0.05, min_px=120):
        self.cfg = type(
            "C",
            (),
            {
                "match_threshold": thr,
                "match_margin": margin,
                "min_face_px": min_px,
                "yunet_sha256": "y",
                "sface_sha256": "s",
            },
        )()
        self._det_h = det_h
        self._emb_h = emb_h

    def status(self):
        return {
            "detector": {"model_id": "yunet", "model_hash": self._det_h},
            "embedder": {"model_id": "sface", "model_hash": self._emb_h},
            "inference_mode": "REAL",
        }


def test_yunet_change_invalidates_model_pin():
    a = model_hash_from_pipeline(_Pipe(det_h="D1"))
    b = model_hash_from_pipeline(_Pipe(det_h="D2"))
    assert a != b


def test_margin_change_invalidates_threshold_pin():
    a = threshold_id_from_pipeline(_Pipe(margin=0.05))
    b = threshold_id_from_pipeline(_Pipe(margin=0.08))
    assert a != b


def test_gallery_revision_changes_when_embedding_bytes_change(tmp_path):
    from app.core.clock import SystemClock
    from app.models.biometric import BiometricEnrollment, FaceTemplate
    from app.vision.faces.template_store import FaceTemplateStore

    engine = create_engine(f"sqlite:///{tmp_path / 'g.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    store = FaceTemplateStore(tmp_path / "data", SystemClock())
    with factory() as db:
        from app.models.entities import Employee

        now = datetime.now(timezone.utc)
        emp = Employee(
            code="G1",
            full_name="Gallery",
            active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(emp)
        db.flush()
        enr = BiometricEnrollment(
            employee_id=emp.id,
            authorization_ref="r",
            authorization_ack_vi="ack đủ dài",
            enrolled_by="t",
            model_id="m",
            model_hash="h",
            status="ACTIVE",
            source="DEMO",
            enrolled_at=now,
        )
        db.add(enr)
        db.flush()
        v1 = np.ones(8, dtype=np.float32)
        tmpl = store.save_template(
            db,
            enrollment_id=enr.id,
            vec=v1,
            quality_score=1.0,
            quality_metadata={},
            vector_version="v1",
            active=True,
        )
        db.commit()
        snap1 = load_active_gallery(db, store)
        # Replace embedding content keeping same id/version fields
        v2 = np.full(8, 2.0, dtype=np.float32)
        ct, nonce = store.encrypt_embedding(v2)
        tmpl.encrypted_embedding = ct
        tmpl.nonce = nonce
        db.commit()
        snap2 = load_active_gallery(db, store)
        assert snap1.revision != snap2.revision

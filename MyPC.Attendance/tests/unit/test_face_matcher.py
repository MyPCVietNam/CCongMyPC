"""P01 face matcher / quality / encryption unit tests."""

from __future__ import annotations

import numpy as np

from app.vision.faces.embedder import FaceEmbedder
from app.vision.faces.matcher import match_embedding
from app.vision.faces.quality import evaluate_face_quality
from app.vision.faces.types import FaceBox, MatchOutcome


def test_match_known_identity():
    emb = FaceEmbedder(None)
    a = emb.embed_identity_fixture("emp-A")
    b = emb.embed_identity_fixture("emp-B")
    probe = emb.embed_identity_fixture("emp-A", quality_noise=0.01)
    result = match_embedding(probe, [(1, a), (2, b)], threshold=0.35, margin=0.05)
    assert result.outcome == MatchOutcome.MATCH
    assert result.employee_id == 1


def test_unknown_face():
    emb = FaceEmbedder(None)
    a = emb.embed_identity_fixture("emp-A")
    probe = emb.embed_identity_fixture("stranger-Z")
    result = match_embedding(probe, [(1, a)], threshold=0.85, margin=0.05)
    assert result.outcome == MatchOutcome.UNKNOWN
    assert result.employee_id is None


def test_ambiguous_close_scores():
    emb = FaceEmbedder(None)
    # Force nearly identical gallery vectors
    base = emb.embed_identity_fixture("twin-base")
    twin = base.copy()
    twin[0] += 0.001
    twin = twin / np.linalg.norm(twin)
    probe = base
    result = match_embedding(probe, [(1, base), (2, twin)], threshold=0.3, margin=0.05)
    assert result.outcome == MatchOutcome.AMBIGUOUS
    assert result.employee_id is None


def test_quality_rejects_small_and_multi():
    box = FaceBox(10, 10, 20, 20)
    q = evaluate_face_quality(640, 360, box, min_face_px=40, face_count=1)
    assert q.ok is False
    q2 = evaluate_face_quality(640, 360, FaceBox(100, 100, 80, 80), face_count=2)
    assert q2.ok is False
    assert "nhiều khuôn mặt" in q2.reasons_vi[0].lower() or "nhiều" in q2.reasons_vi[0]


def test_template_encryption_roundtrip(tmp_path):
    from app.core.clock import FrozenClock, local_wall
    from app.core.database import Base, create_db_engine, make_session_factory
    from app.models import biometric as _b  # noqa: F401
    from app.models import entities as _e  # noqa: F401
    from app.vision.faces.template_store import FaceTemplateStore

    engine = create_db_engine(f"sqlite:///{tmp_path / 't.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    clock = FrozenClock(local_wall(2026, 3, 2, 12, 0, 0))
    store = FaceTemplateStore(tmp_path, clock)
    emb = FaceEmbedder(None).embed_identity_fixture("sec")
    with factory() as session:
        # Need enrollment row FK — create minimal
        from app.models.biometric import BiometricEnrollment
        from app.models.entities import Employee

        emp = Employee(
            code="E1",
            full_name="Test",
            created_at=clock.now_utc(),
            updated_at=clock.now_utc(),
        )
        session.add(emp)
        session.flush()
        enr = BiometricEnrollment(
            employee_id=emp.id,
            enrolled_at=clock.now_utc(),
            authorization_ack_vi="Đã xác nhận",
        )
        session.add(enr)
        session.flush()
        tmpl = store.save_template(
            session,
            enrollment_id=enr.id,
            vec=emb,
            quality_score=0.9,
            quality_metadata={},
            vector_version="synth",
        )
        session.commit()
        # Cleartext should not appear in encrypted blob
        assert b"sec" not in tmpl.encrypted_embedding
        restored = store.decrypt_embedding(tmpl.encrypted_embedding, tmpl.nonce)
        assert np.allclose(restored, emb, atol=1e-5)

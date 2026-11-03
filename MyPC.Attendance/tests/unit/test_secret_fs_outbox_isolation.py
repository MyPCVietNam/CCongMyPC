"""P0-01: session-scoped secret outbox — unrelated commits must not drain each other."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.entities import CameraDevice, SecretFsOutbox
from app.services.secret_fs_outbox import (
    abort_outbox_after_rollback,
    apply_outbox_after_commit,
    queue_delete,
    queue_promote,
)
from app.services.secrets_store import SecretsStore


def _sm(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'iso.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _cam(**kwargs) -> CameraDevice:
    kwargs.setdefault("created_at", datetime.now(timezone.utc))
    kwargs.setdefault("mock_mode", True)
    kwargs.setdefault("enabled", True)
    return CameraDevice(**kwargs)


def test_interleaved_b_commit_does_not_delete_a_secret(tmp_path: Path):
    """REPRODUCTION.txt scenario: B commit must not scrub A's queued delete before A commits."""
    secrets = SecretsStore(tmp_path / "data")
    ref_a = secrets.put_camera_secret(101, "admin", "SecretA!!11")
    sm = _sm(tmp_path)

    with sm() as sess_a:
        sess_a.add(_cam(id=101, name="A", host="10.0.0.1", secret_ref=ref_a))
        sess_a.commit()

    with sm() as sess_a:
        queue_delete(sess_a, ref_a, camera_id=101)
        # Request B unrelated empty commit
        with sm() as sess_b:
            failures_b = apply_outbox_after_commit(secrets, sess_b)
            assert failures_b == []
        assert secrets.has_secret(ref_a)
        # A rolls back — live delete never committed
        sess_a.rollback()
        abort_outbox_after_rollback(secrets, sess_a)

    assert secrets.has_secret(ref_a)
    with sm() as db:
        assert db.scalars(select(SecretFsOutbox)).all() == []


def test_a_commit_deletes_only_own_queued_ref(tmp_path: Path):
    secrets = SecretsStore(tmp_path / "data")
    ref_a = secrets.put_camera_secret(201, "admin", "SecretA!!22")
    ref_b = secrets.put_camera_secret(202, "admin", "SecretB!!22")
    sm = _sm(tmp_path)
    with sm() as db:
        db.add(_cam(id=201, name="A", host="10.0.0.2", secret_ref=ref_a))
        db.add(_cam(id=202, name="B", host="10.0.0.3", secret_ref=ref_b))
        db.commit()

    with sm() as sess_a:
        queue_delete(sess_a, ref_a, camera_id=201)
        db_cam = sess_a.get(CameraDevice, 201)
        db_cam.secret_ref = ""
        sess_a.commit()
        apply_outbox_after_commit(secrets, sess_a)

    with sm() as sess_b:
        queue_delete(sess_b, ref_b, camera_id=202)
        # B rolls back — B credential survives
        sess_b.rollback()
        abort_outbox_after_rollback(secrets, sess_b)

    assert not secrets.has_secret(ref_a)
    assert secrets.has_secret(ref_b)


def test_promote_only_after_commit_preserves_live_on_rollback(tmp_path: Path):
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(303)
    secrets.put_camera_secret(303, "admin", "OldPass!!33")
    sm = _sm(tmp_path)
    with sm() as db:
        db.add(_cam(id=303, name="C", host="10.0.0.4", secret_ref=live))
        db.commit()

    with sm() as sess:
        staged = secrets.stage_camera_secret(303, "admin", "NewPass!!33")
        assert secrets.get_camera_secret(live)["password"] == "OldPass!!33"
        queue_promote(sess, staged_ref=staged, live_ref=live, camera_id=303, secrets=secrets)
        sess.rollback()
        abort_outbox_after_rollback(secrets, sess)

    assert secrets.get_camera_secret(live)["password"] == "OldPass!!33"
    assert not secrets.has_secret(staged)


def test_promote_after_commit_replaces_live(tmp_path: Path):
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(304)
    secrets.put_camera_secret(304, "admin", "OldPass!!44")
    sm = _sm(tmp_path)
    with sm() as db:
        db.add(_cam(id=304, name="D", host="10.0.0.5", secret_ref=live))
        db.commit()

    with sm() as sess:
        staged = secrets.stage_camera_secret(304, "admin", "NewPass!!44")
        queue_promote(sess, staged_ref=staged, live_ref=live, camera_id=304, secrets=secrets)
        sess.commit()
        apply_outbox_after_commit(secrets, sess)

    assert secrets.get_camera_secret(live)["password"] == "NewPass!!44"
    assert not secrets.has_secret(staged)

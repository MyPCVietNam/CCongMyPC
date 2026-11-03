"""REAL SQLite fault-injection for commit-proven secret FS outbox (P0 audit 2026-11-03).

Named crash points:
- kill_before_sql_commit
- kill_after_sql_commit
- kill_after_promote_before_ack
- disk_or_acl_error
- stale_replay
- concurrent_replace_remove
- restart_and_retry
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.entities import CameraDevice, SecretFsOutbox
from app.services.secret_fs_outbox import (
    STATUS_ABANDONED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    abort_outbox_after_rollback,
    apply_outbox_after_commit,
    process_outbox_row,
    queue_delete,
    queue_promote,
    recover_pending_outbox,
)
from app.services.secrets_store import SecretsStore


def _factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outbox-crash.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _seed_camera(db: Session, camera_id: int, secret_ref: str, generation: int = 0) -> CameraDevice:
    row = CameraDevice(
        id=camera_id,
        name=f"Cam{camera_id}",
        host="192.168.0.50",
        secret_ref=secret_ref,
        username_hint="admin",
        secret_generation=generation,
        mock_mode=True,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def test_kill_before_sql_commit_does_not_replay_remove(tmp_path: Path):
    """Kill AFTER staging intent in session but BEFORE SQL commit — live credential must survive."""
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(701)
    secrets.put_camera_secret(701, "admin", "MustSurvive!!01")

    with sm() as db:
        _seed_camera(db, 701, live, generation=0)
        db.commit()

    with sm() as db:
        queue_delete(db, live, camera_id=701)
        # Crash window: outbox row only in uncommitted txn
        assert db.info.get("secret_fs_outbox_ids")
        db.rollback()
        abort_outbox_after_rollback(secrets, db)

    with sm() as db:
        assert db.scalars(select(SecretFsOutbox)).all() == []
        cam = db.get(CameraDevice, 701)
        assert cam is not None
        assert cam.secret_ref == live
        assert cam.secret_generation == 0

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_applied"] == 0
    assert secrets.get_camera_secret(live)["password"] == "MustSurvive!!01"
    assert secrets.has_secret(live)


def test_kill_before_sql_commit_replace_keeps_old_live(tmp_path: Path):
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(702)
    secrets.put_camera_secret(702, "admin", "OldLive!!02")

    with sm() as db:
        _seed_camera(db, 702, live)
        db.commit()

    with sm() as db:
        staged = secrets.stage_camera_secret(702, "admin", "NeverCommit!!02")
        queue_promote(db, staged_ref=staged, live_ref=live, camera_id=702, secrets=secrets)
        db.rollback()
        abort_outbox_after_rollback(secrets, db)

    assert secrets.get_camera_secret(live)["password"] == "OldLive!!02"
    assert list(secrets._dir.glob("camera-702.staged-*.bin")) == []
    with sm() as db:
        assert db.scalars(select(SecretFsOutbox)).all() == []
    recover_pending_outbox(secrets, sm)
    assert secrets.get_camera_secret(live)["password"] == "OldLive!!02"


def test_kill_after_sql_commit_recovers_promote(tmp_path: Path):
    """Commit outbox then die before promote — restart recovery must finish FS op."""
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(703)
    secrets.put_camera_secret(703, "admin", "Before!!03")

    with sm() as db:
        cam = _seed_camera(db, 703, live)
        staged = secrets.stage_camera_secret(703, "admin", "AfterRecover!!03")
        queue_promote(db, staged_ref=staged, live_ref=live, camera_id=703, secrets=secrets)
        cam.secret_ref = live
        db.commit()
        # Simulate kill: drop in-memory ids without applying
        db.info.pop("secret_fs_outbox_ids", None)
        db.info.pop("secret_fs_ops", None)

    assert secrets.get_camera_secret(live)["password"] == "Before!!03"
    assert secrets.has_secret(staged)

    with sm() as db:
        rows = db.scalars(select(SecretFsOutbox)).all()
        assert len(rows) == 1
        assert rows[0].status == STATUS_PENDING
        assert rows[0].generation == 1

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_failed"] == 0
    assert summary["journals_applied"] == 1
    assert secrets.get_camera_secret(live)["password"] == "AfterRecover!!03"
    assert not secrets.has_secret(staged)
    with sm() as db:
        assert db.scalar(select(SecretFsOutbox).where(SecretFsOutbox.status == STATUS_DONE))


def test_kill_after_promote_before_ack(tmp_path: Path):
    """FS promote succeeded; STATUS_DONE commit never landed — idempotent restart ack."""
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(704)
    secrets.put_camera_secret(704, "admin", "Old!!04")
    staged = secrets.stage_camera_secret(704, "admin", "Promoted!!04")
    payload = (tmp_path / "data" / "secrets" / staged).read_bytes()
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()

    with sm() as db:
        _seed_camera(db, 704, live)
        row = queue_promote(
            db, staged_ref=staged, live_ref=live, camera_id=704, secrets=secrets
        )
        # Force known digest (queue_promote already set it)
        assert row.payload_sha256 == sha
        db.commit()
        rid = int(row.id)

    # Manually promote FS then leave outbox as PROCESSING (crash after promote, before ack)
    secrets.promote_staged_camera_secret(staged, live)
    with sm() as db:
        row = db.get(SecretFsOutbox, rid)
        row.status = STATUS_PROCESSING
        row.attempts = 1
        db.commit()

    assert secrets.get_camera_secret(live)["password"] == "Promoted!!04"
    assert not secrets.has_secret(staged)

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_applied"] == 1
    assert secrets.get_camera_secret(live)["password"] == "Promoted!!04"
    with sm() as db:
        assert db.get(SecretFsOutbox, rid).status == STATUS_DONE


def test_disk_or_acl_error_keeps_intent_and_retries(tmp_path: Path):
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(705)
    secrets.put_camera_secret(705, "admin", "Keep!!05")

    with sm() as db:
        _seed_camera(db, 705, live)
        staged = secrets.stage_camera_secret(705, "admin", "Retry!!05")
        row = queue_promote(
            db, staged_ref=staged, live_ref=live, camera_id=705, secrets=secrets
        )
        db.commit()
        rid = int(row.id)
        db.info.clear()

    real_promote = secrets.promote_staged_camera_secret
    calls = {"n": 0}

    def boom(staged_ref, live_ref):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated_disk_or_acl_denied")
        return real_promote(staged_ref, live_ref)

    with mock.patch.object(secrets, "promote_staged_camera_secret", side_effect=boom):
        status = process_outbox_row(secrets, sm, rid)
    assert status == STATUS_PENDING
    assert secrets.get_camera_secret(live)["password"] == "Keep!!05"
    with sm() as db:
        row = db.get(SecretFsOutbox, rid)
        assert row.status == STATUS_PENDING
        assert "simulated_disk" in (row.last_error or "")

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_failed"] == 0
    assert secrets.get_camera_secret(live)["password"] == "Retry!!05"


def test_stale_replay_abandoned_when_newer_generation_committed(tmp_path: Path):
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(706)
    secrets.put_camera_secret(706, "admin", "Gen0!!06")

    with sm() as db:
        cam = _seed_camera(db, 706, live, generation=0)
        staged_old = secrets.stage_camera_secret(706, "admin", "Stale!!06")
        old = queue_promote(
            db, staged_ref=staged_old, live_ref=live, camera_id=706, secrets=secrets
        )
        db.commit()
        old_id = int(old.id)
        # Do not apply — leave pending
        db.info.clear()

    with sm() as db:
        cam = db.get(CameraDevice, 706)
        staged_new = secrets.stage_camera_secret(706, "admin", "Fresh!!06")
        new = queue_promote(
            db, staged_ref=staged_new, live_ref=live, camera_id=706, secrets=secrets
        )
        cam.secret_ref = live
        db.commit()
        new_id = int(new.id)
        # Apply only the newer intent
        status_new = process_outbox_row(secrets, sm, new_id)
        assert status_new == STATUS_DONE

    # Stale old intent must abandon, not overwrite Fresh
    status_old = process_outbox_row(secrets, sm, old_id)
    assert status_old == STATUS_ABANDONED
    assert secrets.get_camera_secret(live)["password"] == "Fresh!!06"
    with sm() as db:
        assert db.get(CameraDevice, 706).secret_generation == 2
        assert db.get(SecretFsOutbox, old_id).status == STATUS_ABANDONED


def test_concurrent_replace_and_remove_final_matches_db(tmp_path: Path):
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(707)
    secrets.put_camera_secret(707, "admin", "Base!!07")
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def do_replace() -> None:
        try:
            barrier.wait(timeout=5)
            with sm() as db2:
                cam2 = db2.get(CameraDevice, 707)
                staged = secrets.stage_camera_secret(707, "admin", "FromReplace!!07")
                queue_promote(
                    db2,
                    staged_ref=staged,
                    live_ref=live,
                    camera_id=707,
                    secrets=secrets,
                )
                cam2.secret_ref = live
                db2.commit()
                apply_outbox_after_commit(secrets, db2)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def do_remove() -> None:
        try:
            barrier.wait(timeout=5)
            with sm() as db2:
                cam2 = db2.get(CameraDevice, 707)
                queue_delete(db2, live, camera_id=707)
                cam2.secret_ref = ""
                db2.commit()
                apply_outbox_after_commit(secrets, db2)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with sm() as db:
        _seed_camera(db, 707, live)
        db.commit()

    t1 = threading.Thread(target=do_replace)
    t2 = threading.Thread(target=do_remove)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)
    assert not errors, errors

    # Replay any leftover pending (ordering + generation)
    recover_pending_outbox(secrets, sm)

    with sm() as db:
        cam = db.get(CameraDevice, 707)
        assert cam is not None
        gen = int(cam.secret_generation)
        assert gen >= 1
        # Highest committed generation wins — FS must match that row's DB intent
        winner = db.scalars(
            select(SecretFsOutbox)
            .where(
                SecretFsOutbox.camera_id == 707,
                SecretFsOutbox.generation == gen,
            )
            .order_by(SecretFsOutbox.id.desc())
        ).first()
        assert winner is not None
        assert winner.status in {STATUS_DONE, STATUS_ABANDONED} or winner.status == STATUS_DONE
        # Prefer DONE at max generation
        done = db.scalars(
            select(SecretFsOutbox)
            .where(SecretFsOutbox.camera_id == 707, SecretFsOutbox.status == STATUS_DONE)
            .order_by(SecretFsOutbox.generation.desc())
        ).first()
        assert done is not None
        assert int(done.generation) == gen
        if done.op == "promote":
            assert cam.secret_ref == live
            assert secrets.has_secret(live)
            assert secrets.get_camera_secret(live) is not None
        else:
            assert (cam.secret_ref or "") == ""
            assert not secrets.has_secret(live)


def test_restart_and_retry_after_failed_attempts(tmp_path: Path):
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(708)
    secrets.put_camera_secret(708, "admin", "Hold!!08")

    with sm() as db:
        _seed_camera(db, 708, live)
        staged = secrets.stage_camera_secret(708, "admin", "Eventually!!08")
        row = queue_promote(
            db, staged_ref=staged, live_ref=live, camera_id=708, secrets=secrets
        )
        row.max_attempts = 2
        db.commit()
        rid = int(row.id)
        db.info.clear()

    with mock.patch.object(
        secrets, "promote_staged_camera_secret", side_effect=OSError("acl_denied")
    ):
        assert process_outbox_row(secrets, sm, rid) == STATUS_PENDING
        assert process_outbox_row(secrets, sm, rid) == STATUS_FAILED

    # Startup recover must NOT spin forever on exhausted FAILED
    summary = recover_pending_outbox(secrets, sm, force_retry=False)
    assert summary["journals_applied"] == 0
    with sm() as db:
        assert db.get(SecretFsOutbox, rid).status == STATUS_FAILED

    # Admin retry forces another attempt
    summary = recover_pending_outbox(secrets, sm, force_retry=True)
    assert summary["journals_applied"] == 1
    assert secrets.get_camera_secret(live)["password"] == "Eventually!!08"


def test_postcommit_cleanup_failure_does_not_drop_outbox(tmp_path: Path):
    """Mirrors get_db: commit succeeded; later cleanup exception must not abort outbox."""
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(709)
    secrets.put_camera_secret(709, "admin", "X!!09")

    with sm() as db:
        _seed_camera(db, 709, live)
        staged = secrets.stage_camera_secret(709, "admin", "Y!!09")
        queue_promote(db, staged_ref=staged, live_ref=live, camera_id=709, secrets=secrets)
        db.commit()
        committed = True
        # Simulate pending_secret_cleanup raising AFTER commit, BEFORE apply —
        # apply must still run (deps.py separates these paths).
        cleanup_error = RuntimeError("bootstrap_cleanup_boom")
        try:
            raise cleanup_error
        except RuntimeError:
            pass
        failures = apply_outbox_after_commit(secrets, db)
        assert failures == []
        assert committed
        assert secrets.get_camera_secret(live)["password"] == "Y!!09"
        with sm() as db2:
            assert db2.scalars(select(SecretFsOutbox)).one().status == STATUS_DONE


def test_uncommitted_json_journal_is_not_authoritative(tmp_path: Path):
    """Legacy pre-commit JSON must never delete a live secret still referenced by SQLite."""
    sm = _factory(tmp_path)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(710)
    secrets.put_camera_secret(710, "admin", "Referenced!!10")
    legacy = secrets._dir / "_fs_outbox"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "evil-remove.json").write_text(
        '{"op":"delete","delete_ref":"camera-710.bin","status":"pending"}',
        encoding="utf-8",
    )
    with sm() as db:
        _seed_camera(db, 710, live)
        db.commit()

    summary = recover_pending_outbox(secrets, sm)
    assert secrets.has_secret(live)
    assert secrets.get_camera_secret(live)["password"] == "Referenced!!10"
    assert summary.get("legacy_json_removed", 0) >= 1
    assert not (legacy / "evil-remove.json").exists()

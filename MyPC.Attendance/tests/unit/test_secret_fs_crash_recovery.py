"""Crash after SQL commit / before promote — SQLite outbox replay (commit-proven)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.entities import CameraDevice, SecretFsOutbox
from app.services.secret_fs_outbox import (
    STATUS_PENDING,
    apply_outbox_after_commit,
    process_outbox_row,
    queue_promote,
    recover_pending_outbox,
)
from app.services.secrets_store import SecretsStore


def _sm(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crash.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_crash_between_commit_and_promote_recovers_on_restart(tmp_path: Path):
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(501)
    secrets.put_camera_secret(501, "admin", "BeforeCrash!!1")
    sm = _sm(tmp_path)

    with sm() as db:
        db.add(
            CameraDevice(
                id=501,
                name="Crash",
                host="10.0.0.51",
                secret_ref=live,
                mock_mode=True,
                enabled=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        staged = secrets.stage_camera_secret(501, "admin", "AfterRecover!!2")
        queue_promote(db, staged_ref=staged, live_ref=live, camera_id=501, secrets=secrets)
        db.commit()
        # Kill: forget in-memory apply list (simulate process death after commit)
        db.info.clear()

    assert secrets.get_camera_secret(live)["password"] == "BeforeCrash!!1"
    assert secrets.has_secret(staged)
    with sm() as db:
        assert db.scalars(select(SecretFsOutbox)).one().status == STATUS_PENDING

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_failed"] == 0
    assert secrets.get_camera_secret(live)["password"] == "AfterRecover!!2"
    assert not secrets.has_secret(staged)


def test_post_commit_fs_failure_is_observable_and_retriable(tmp_path: Path):
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(502)
    secrets.put_camera_secret(502, "admin", "Keep!!3")
    sm = _sm(tmp_path)

    with sm() as db:
        db.add(
            CameraDevice(
                id=502,
                name="Retry",
                host="10.0.0.52",
                secret_ref=live,
                mock_mode=True,
                enabled=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        staged = secrets.stage_camera_secret(502, "admin", "New!!3")
        row = queue_promote(db, staged_ref=staged, live_ref=live, camera_id=502, secrets=secrets)
        db.commit()
        rid = int(row.id)
        db.info.clear()

    real_promote = secrets.promote_staged_camera_secret
    calls = {"n": 0}

    def boom(staged_ref, live_ref):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated_disk_full")
        return real_promote(staged_ref, live_ref)

    with mock.patch.object(secrets, "promote_staged_camera_secret", side_effect=boom):
        status = process_outbox_row(secrets, sm, rid)
    assert status == STATUS_PENDING
    assert secrets.get_camera_secret(live)["password"] == "Keep!!3"
    with sm() as db:
        assert db.get(SecretFsOutbox, rid).status == STATUS_PENDING

    summary = recover_pending_outbox(secrets, sm)
    assert summary["journals_failed"] == 0
    assert secrets.get_camera_secret(live)["password"] == "New!!3"

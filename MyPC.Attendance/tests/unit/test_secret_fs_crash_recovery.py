"""Crash after SQL commit / before promote — durable journal replay."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from app.services.secret_fs_outbox import (
    SESSION_KEY,
    apply_outbox_after_commit,
    queue_promote,
    recover_pending_journals,
    write_durable_journal,
)
from app.services.secrets_store import SecretsStore


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


def test_crash_between_commit_and_promote_recovers_on_restart(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    live = secrets.live_camera_ref(501)
    secrets.put_camera_secret(501, "admin", "BeforeCrash!!1")
    sess = _FakeSession()
    staged = secrets.stage_camera_secret(501, "admin", "AfterRecover!!2")
    queue_promote(sess, staged_ref=staged, live_ref=live, camera_id=501)  # type: ignore[arg-type]

    # Pre-commit durable journal (as get_db does)
    journal = write_durable_journal(secrets, sess)  # type: ignore[arg-type]
    assert journal is not None and journal.exists()

    # Simulate process kill: drop in-memory outbox without applying
    sess.info.pop(SESSION_KEY, None)
    # Live still old; staged still present
    assert secrets.get_camera_secret(live)["password"] == "BeforeCrash!!1"
    assert secrets.has_secret(staged)

    # Restart recovery
    summary = recover_pending_journals(secrets)
    assert summary["journals_failed"] == 0
    assert secrets.get_camera_secret(live)["password"] == "AfterRecover!!2"
    assert not secrets.has_secret(staged)
    assert not journal.exists()


def test_post_commit_fs_failure_is_observable_and_retriable(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    live = secrets.live_camera_ref(502)
    secrets.put_camera_secret(502, "admin", "Keep!!3")
    sess = _FakeSession()
    staged = secrets.stage_camera_secret(502, "admin", "New!!3")
    queue_promote(sess, staged_ref=staged, live_ref=live, camera_id=502)  # type: ignore[arg-type]
    write_durable_journal(secrets, sess)  # type: ignore[arg-type]

    real_promote = secrets.promote_staged_camera_secret
    calls = {"n": 0}

    def boom(staged_ref, live_ref):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated_disk_full")
        return real_promote(staged_ref, live_ref)

    with mock.patch.object(secrets, "promote_staged_camera_secret", side_effect=boom):
        failures = apply_outbox_after_commit(secrets, sess)  # type: ignore[arg-type]
    assert failures
    assert secrets.get_camera_secret(live)["password"] == "Keep!!3"
    # Journal retained
    pending = list((secrets._dir / "_fs_outbox").glob("*.json"))
    assert pending

    # Retry succeeds
    summary = recover_pending_journals(secrets)
    assert summary["journals_failed"] == 0
    assert secrets.get_camera_secret(live)["password"] == "New!!3"

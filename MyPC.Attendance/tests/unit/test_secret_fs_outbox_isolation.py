"""P0-01: session-scoped secret outbox — unrelated commits must not drain each other."""

from __future__ import annotations

from pathlib import Path

from app.services.secret_fs_outbox import (
    SESSION_KEY,
    abort_outbox_after_rollback,
    apply_outbox_after_commit,
    queue_delete,
    queue_promote,
)
from app.services.secrets_store import SecretsStore


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


def test_interleaved_b_commit_does_not_delete_a_secret(tmp_path: Path):
    """REPRODUCTION.txt scenario: B commit must not scrub A's queued delete before A commits."""
    secrets = SecretsStore(tmp_path)
    # Live secret for camera A
    ref_a = secrets.put_camera_secret(101, "admin", "SecretA!!11")
    assert secrets.has_secret(ref_a)

    sess_a = _FakeSession()
    sess_b = _FakeSession()

    # Request A queues delete of camera-A (hard-delete path) but has NOT committed
    queue_delete(sess_a, ref_a)  # type: ignore[arg-type]

    # Request B does unrelated work with empty outbox and "commits"
    failures_b = apply_outbox_after_commit(secrets, sess_b)  # type: ignore[arg-type]
    assert failures_b == []
    # A's credential must still exist — B must not have drained A's queue
    assert secrets.has_secret(ref_a)

    # A rolls back — discard only staged markers; live delete dropped
    abort_outbox_after_rollback(secrets, sess_a)  # type: ignore[arg-type]
    assert secrets.has_secret(ref_a)
    assert sess_a.info.get(SESSION_KEY) in (None, [])


def test_a_commit_deletes_only_own_queued_ref(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    ref_a = secrets.put_camera_secret(201, "admin", "SecretA!!22")
    ref_b = secrets.put_camera_secret(202, "admin", "SecretB!!22")
    sess_a = _FakeSession()
    sess_b = _FakeSession()
    queue_delete(sess_a, ref_a)  # type: ignore[arg-type]
    queue_delete(sess_b, ref_b)  # type: ignore[arg-type]

    apply_outbox_after_commit(secrets, sess_a)  # type: ignore[arg-type]
    assert not secrets.has_secret(ref_a)
    assert secrets.has_secret(ref_b)

    abort_outbox_after_rollback(secrets, sess_b)  # type: ignore[arg-type]
    assert secrets.has_secret(ref_b)


def test_promote_only_after_commit_preserves_live_on_rollback(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    live = secrets.live_camera_ref(303)
    secrets.put_camera_secret(303, "admin", "OldPass!!33")
    old = secrets.get_camera_secret(live)
    assert old and old["password"] == "OldPass!!33"

    sess = _FakeSession()
    staged = secrets.stage_camera_secret(303, "admin", "NewPass!!33")
    assert staged != live
    assert secrets.has_secret(staged)
    # Live unchanged while staged exists
    assert secrets.get_camera_secret(live)["password"] == "OldPass!!33"

    queue_promote(sess, staged_ref=staged, live_ref=live)  # type: ignore[arg-type]
    abort_outbox_after_rollback(secrets, sess)  # type: ignore[arg-type]
    assert secrets.get_camera_secret(live)["password"] == "OldPass!!33"
    assert not secrets.has_secret(staged)


def test_promote_after_commit_replaces_live(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    live = secrets.live_camera_ref(304)
    secrets.put_camera_secret(304, "admin", "OldPass!!44")
    sess = _FakeSession()
    staged = secrets.stage_camera_secret(304, "admin", "NewPass!!44")
    queue_promote(sess, staged_ref=staged, live_ref=live)  # type: ignore[arg-type]
    apply_outbox_after_commit(secrets, sess)  # type: ignore[arg-type]
    assert secrets.get_camera_secret(live)["password"] == "NewPass!!44"
    assert not secrets.has_secret(staged)

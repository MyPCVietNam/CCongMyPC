"""Concurrent REPLACE on same camera must not leave SQLite/live secret disagreeing."""

from __future__ import annotations

import threading
from pathlib import Path

from app.services.secret_fs_outbox import (
    apply_outbox_after_commit,
    queue_promote,
    write_durable_journal,
)
from app.services.secrets_store import SecretsStore


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


def test_serialized_concurrent_promotes_last_writer_consistent(tmp_path: Path):
    secrets = SecretsStore(tmp_path)
    live = secrets.live_camera_ref(601)
    secrets.put_camera_secret(601, "admin", "Base!!0")
    results: list[str] = []
    errors: list[BaseException] = []

    def worker(tag: str, password: str) -> None:
        try:
            sess = _FakeSession()
            staged = secrets.stage_camera_secret(601, "admin", password)
            queue_promote(sess, staged_ref=staged, live_ref=live, camera_id=601)  # type: ignore[arg-type]
            write_durable_journal(secrets, sess)  # type: ignore[arg-type]
            # Hold lock across "commit" boundary then promote
            failures = apply_outbox_after_commit(secrets, sess)  # type: ignore[arg-type]
            assert not failures
            results.append(tag)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("A", "PassA!!11"))
    t2 = threading.Thread(target=worker, args=("B", "PassB!!22"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errors, errors
    assert set(results) == {"A", "B"}
    # Live file is one of the two passwords — never empty/corrupt; no staged leftovers
    final = secrets.get_camera_secret(live)
    assert final is not None
    assert final["password"] in {"PassA!!11", "PassB!!22"}
    assert list(secrets._dir.glob("camera-601.staged-*.bin")) == []

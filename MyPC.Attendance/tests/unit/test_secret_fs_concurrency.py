"""Concurrent REPLACE on same camera — final live secret must match highest committed generation."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.entities import CameraDevice, SecretFsOutbox
from app.services.secret_fs_outbox import (
    STATUS_DONE,
    apply_outbox_after_commit,
    queue_promote,
    recover_pending_outbox,
)
from app.services.secrets_store import SecretsStore


def test_serialized_concurrent_promotes_last_writer_consistent(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'conc.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    secrets = SecretsStore(tmp_path / "data")
    live = secrets.live_camera_ref(601)
    secrets.put_camera_secret(601, "admin", "Base!!0")
    with sm() as db:
        db.add(
            CameraDevice(
                id=601,
                name="Conc",
                host="10.0.0.61",
                secret_ref=live,
                mock_mode=True,
                enabled=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    results: list[str] = []
    errors: list[BaseException] = []
    passwords = {"A": "PassA!!11", "B": "PassB!!22"}

    def worker(tag: str, password: str) -> None:
        try:
            with sm() as sess:
                staged = secrets.stage_camera_secret(601, "admin", password)
                queue_promote(
                    sess, staged_ref=staged, live_ref=live, camera_id=601, secrets=secrets
                )
                cam = sess.get(CameraDevice, 601)
                cam.secret_ref = live
                sess.commit()
                failures = apply_outbox_after_commit(secrets, sess)
                assert not failures, failures
                results.append(tag)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("A", passwords["A"]))
    t2 = threading.Thread(target=worker, args=("B", passwords["B"]))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)
    assert not errors, errors
    assert set(results) == {"A", "B"}

    recover_pending_outbox(secrets, sm)

    with sm() as db:
        cam = db.get(CameraDevice, 601)
        assert cam is not None
        top = db.scalars(
            select(SecretFsOutbox)
            .where(SecretFsOutbox.camera_id == 601, SecretFsOutbox.status == STATUS_DONE)
            .order_by(SecretFsOutbox.generation.desc())
        ).first()
        assert top is not None
        assert int(cam.secret_generation) == int(top.generation)
        final = secrets.get_camera_secret(live)
        assert final is not None
        import hashlib

        live_sha = hashlib.sha256((secrets._dir / live).read_bytes()).hexdigest()
        assert live_sha == top.payload_sha256
        assert final["password"] in set(passwords.values())
    assert list(secrets._dir.glob("camera-601.staged-*.bin")) == []

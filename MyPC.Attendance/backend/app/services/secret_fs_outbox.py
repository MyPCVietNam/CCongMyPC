"""Commit-proven SQLite outbox for camera credential filesystem ops.

P0: Never replay intents that were not committed with the camera state update.
Staging blobs may exist before commit; promote/delete run ONLY for committed
SecretFsOutbox rows. Generation guards prevent stale replay over newer credentials.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CameraDevice, SecretFsOutbox
from app.services.secrets_store import SecretsStore

logger = logging.getLogger(__name__)

SESSION_KEY = "secret_fs_ops"  # in-memory staged discard markers only
LOCKS_KEY = "credential_locks_held"
OUTBOX_IDS_KEY = "secret_fs_outbox_ids"
RUNTIME_COMPENSATE_KEY = "runtime_compensate"
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_ABANDONED = "abandoned"
MAX_ATTEMPTS_DEFAULT = 8
# Staged blobs younger than this are never scrubbed as orphans during exclusive maintenance
STAGED_ORPHAN_MAX_AGE_SEC = 3600

# In-process leases: staged refs owned by in-flight (possibly uncommitted) requests
_ACTIVE_STAGED_LOCK = threading.Lock()
_ACTIVE_STAGED: set[str] = set()


def _lease_dir(secrets: SecretsStore) -> Path:
    d = secrets._dir / "_staging_leases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def register_active_staged(secrets: SecretsStore, staged_ref: str) -> None:
    """Mark staged blob as owned by an in-flight request (C11)."""
    if not staged_ref or ".staged-" not in staged_ref:
        return
    with _ACTIVE_STAGED_LOCK:
        _ACTIVE_STAGED.add(staged_ref)
    lease = _lease_dir(secrets) / f"{staged_ref}.lease"
    try:
        lease.write_text(
            f"{os.getpid()}:{datetime.now(timezone.utc).isoformat()}",
            encoding="utf-8",
        )
    except OSError:
        pass


def unregister_active_staged(secrets: SecretsStore, staged_ref: str) -> None:
    if not staged_ref:
        return
    with _ACTIVE_STAGED_LOCK:
        _ACTIVE_STAGED.discard(staged_ref)
    lease = secrets._dir / "_staging_leases" / f"{staged_ref}.lease"
    try:
        if lease.exists():
            lease.unlink()
    except OSError:
        pass


def _is_staged_leased(
    secrets: SecretsStore, staged_ref: str, *, max_lease_age_sec: int | None = None
) -> bool:
    with _ACTIVE_STAGED_LOCK:
        if staged_ref in _ACTIVE_STAGED:
            return True
    lease = secrets._dir / "_staging_leases" / f"{staged_ref}.lease"
    if not lease.exists():
        return False
    if max_lease_age_sec is not None:
        import time

        try:
            if time.time() - lease.stat().st_mtime > max_lease_age_sec:
                # Stale durable lease from a crashed process — allow exclusive scrub
                return False
        except OSError:
            return False
    return True


class CameraCredentialLockTable:
    """Per-camera in-process mutex. RLock so post-commit apply can re-enter safely."""

    def __init__(self) -> None:
        self._meta = threading.Lock()
        self._locks: dict[int, threading.RLock] = {}

    def acquire(self, camera_id: int) -> None:
        cid = int(camera_id)
        with self._meta:
            lock = self._locks.setdefault(cid, threading.RLock())
        lock.acquire()

    def release(self, camera_id: int) -> None:
        cid = int(camera_id)
        with self._meta:
            lock = self._locks.get(cid)
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass


CREDENTIAL_LOCKS = CameraCredentialLockTable()


@contextmanager
def camera_file_lock(secrets: SecretsStore, camera_id: int | None) -> Iterator[None]:
    """Multi-process serialization via flock / msvcrt on a per-camera lock file."""
    if camera_id is None:
        yield
        return
    lock_dir = secrets._dir / "_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"camera-{int(camera_id)}.lock"
    fd = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fd.close()
        except Exception:
            pass


def session_secret_outbox(db: Session) -> list[dict[str, Any]]:
    box = db.info.get(SESSION_KEY)
    if box is None:
        box = []
        db.info[SESSION_KEY] = box
    return box  # type: ignore[return-value]


def acquire_camera_credential_lock(db: Session, camera_id: int) -> None:
    held: list[int] = db.info.setdefault(LOCKS_KEY, [])
    cid = int(camera_id)
    if cid in held:
        return
    CREDENTIAL_LOCKS.acquire(cid)
    held.append(cid)


def release_session_credential_locks(db: Session) -> None:
    held: list[int] = list(db.info.pop(LOCKS_KEY, []) or [])
    for cid in held:
        CREDENTIAL_LOCKS.release(cid)


def register_runtime_compensate(db: Session, fn: Callable[[], None]) -> None:
    db.info.setdefault(RUNTIME_COMPENSATE_KEY, []).append(fn)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_lifecycle_id(row: CameraDevice) -> str:
    lid = (getattr(row, "lifecycle_id", None) or "").strip()
    if not lid:
        lid = uuid.uuid4().hex
        row.lifecycle_id = lid
    return lid


def _next_generation(db: Session, camera_id: int) -> int:
    """Bump monotonic secret_generation under the caller's camera lock.

    Reads the committed generation via a column SELECT (not full entity refresh)
    so dirty name/host/model edits in the same session are preserved (C12).
    Under the per-camera lock, concurrent sessions cannot interleave bumps.
    """
    row = db.get(CameraDevice, camera_id)
    if row is None:
        # Hard-delete path may have removed row — still allow delete outbox with gen bump
        return 1
    # Committed value from DB without expiring dirty attributes on `row`
    committed = db.execute(
        select(CameraDevice.secret_generation).where(CameraDevice.id == camera_id)
    ).scalar_one_or_none()
    base = int(committed or 0)
    # Same-session prior bump (autoflush off) — never regress
    in_mem = int(getattr(row, "secret_generation", 0) or 0)
    gen = max(base, in_mem) + 1
    row.secret_generation = gen
    return gen


def _lifecycle_for_camera(
    db: Session, camera_id: int | None, explicit: str | None = None
) -> str:
    if explicit:
        return explicit
    if camera_id is None:
        return ""
    row = db.get(CameraDevice, camera_id)
    if row is None:
        return ""
    return _ensure_lifecycle_id(row)


def queue_delete(
    db: Session,
    secret_ref: str,
    *,
    camera_id: int | None = None,
    camera_lifecycle_id: str | None = None,
    hard_delete: bool = False,
) -> SecretFsOutbox | None:
    if not secret_ref:
        return None
    if camera_id is not None:
        acquire_camera_credential_lock(db, camera_id)
        gen = _next_generation(db, camera_id)
    else:
        gen = 0
    # Capture lifecycle before/without relying on deleted row (C14 hard-delete)
    lifecycle = camera_lifecycle_id or _lifecycle_for_camera(db, camera_id)
    row = SecretFsOutbox(
        public_id=uuid.uuid4().hex,
        camera_id=camera_id,
        camera_lifecycle_id=lifecycle,
        op="hard_delete_scrub" if hard_delete else "delete",
        delete_ref=secret_ref,
        generation=gen,
        status=STATUS_PENDING,
        attempts=0,
        max_attempts=MAX_ATTEMPTS_DEFAULT,
        created_at=_utc_now(),
    )
    db.add(row)
    db.flush()
    ids: list[int] = db.info.setdefault(OUTBOX_IDS_KEY, [])
    ids.append(int(row.id))
    return row


def queue_promote(
    db: Session,
    *,
    staged_ref: str,
    live_ref: str,
    camera_id: int,
    secrets: SecretsStore | None = None,
) -> SecretFsOutbox:
    if not staged_ref or not live_ref:
        raise ValueError("staged_ref và live_ref bắt buộc")
    acquire_camera_credential_lock(db, camera_id)
    gen = _next_generation(db, camera_id)
    lifecycle = _lifecycle_for_camera(db, camera_id)
    payload_sha = ""
    if secrets is not None:
        path = secrets._dir / staged_ref
        if path.exists():
            payload_sha = _file_sha256(path)
        register_active_staged(secrets, staged_ref)
    # Register rollback discard BEFORE any flush/failure point so staged+lease
    # are always unwound via abort_outbox_after_rollback (CLEANUP-P1).
    session_secret_outbox(db).append(
        {"op": "discard_on_rollback", "ref": staged_ref, "camera_id": int(camera_id)}
    )
    row = SecretFsOutbox(
        public_id=uuid.uuid4().hex,
        camera_id=int(camera_id),
        camera_lifecycle_id=lifecycle,
        op="promote",
        staged_ref=staged_ref,
        live_ref=live_ref,
        generation=gen,
        payload_sha256=payload_sha,
        status=STATUS_PENDING,
        attempts=0,
        max_attempts=MAX_ATTEMPTS_DEFAULT,
        created_at=_utc_now(),
    )
    db.add(row)
    db.flush()
    ids: list[int] = db.info.setdefault(OUTBOX_IDS_KEY, [])
    ids.append(int(row.id))
    return row


def queue_discard_staged(db: Session, staged_ref: str) -> None:
    if staged_ref:
        session_secret_outbox(db).append({"op": "discard_on_rollback", "ref": staged_ref})


def _lifecycle_mismatch(db: Session, row: SecretFsOutbox) -> bool:
    """True when a newer camera instance reused the numeric id (C14)."""
    intent_life = (row.camera_lifecycle_id or "").strip()
    if row.camera_id is None:
        return False
    cam = db.get(CameraDevice, row.camera_id)
    if cam is None:
        # Target instance gone — hard-delete scrub may proceed if lifecycle was recorded
        return False
    live_life = (getattr(cam, "lifecycle_id", None) or "").strip()
    if intent_life and live_life and intent_life != live_life:
        return True
    # Legacy outbox without lifecycle while a new instance exists: refuse DELETE scrub
    if not intent_life and live_life and row.op in {"delete", "hard_delete_scrub"}:
        return True
    return False


def _is_stale(db: Session, row: SecretFsOutbox) -> bool:
    if _lifecycle_mismatch(db, row):
        return True
    if row.camera_id is None:
        return False
    cam = db.get(CameraDevice, row.camera_id)
    if cam is None:
        # Camera hard-deleted — delete/scrub for that lifecycle may still apply
        return False
    # Read generation without full refresh (preserve any dirty session state)
    committed = db.execute(
        select(CameraDevice.secret_generation).where(CameraDevice.id == row.camera_id)
    ).scalar_one_or_none()
    live_gen = int(committed if committed is not None else (getattr(cam, "secret_generation", 0) or 0))
    return int(row.generation) < live_gen


def _apply_one(secrets: SecretsStore, db: Session, row: SecretFsOutbox) -> None:
    if _lifecycle_mismatch(db, row):
        raise RuntimeError("STALE_CAMERA_LIFECYCLE")
    if row.op == "promote":
        staged = row.staged_ref
        live = row.live_ref
        staged_path = secrets._dir / staged
        live_path = secrets._dir / live
        if staged_path.exists():
            secrets.promote_staged_camera_secret(staged, live)
            unregister_active_staged(secrets, staged)
            return
        # Idempotent: staged gone — only ack if live matches recorded payload digest
        if live_path.exists() and row.payload_sha256:
            if _file_sha256(live_path) == row.payload_sha256:
                unregister_active_staged(secrets, staged or "")
                return
            raise FileNotFoundError(
                f"staged missing and live sha mismatch for outbox {row.public_id}"
            )
        if live_path.exists() and not row.payload_sha256:
            # Legacy row without digest — require exact staged presence
            raise FileNotFoundError(f"staged missing for outbox {row.public_id}")
        raise FileNotFoundError(f"staged and live missing: {staged} / {live}")
    if row.op in {"delete", "hard_delete_scrub"}:
        ref = row.delete_ref
        if not ref:
            return
        # If camera still points at a different live secret, do not delete that file
        if row.camera_id is not None:
            cam = db.get(CameraDevice, row.camera_id)
            if cam is not None and (cam.secret_ref or "") and cam.secret_ref != ref:
                # Stale delete target — abandon
                raise RuntimeError("STALE_DELETE_REF")
            # Credential REMOVE on living camera: allow. Hard-delete scrub when cam
            # exists with matching lifecycle is unusual (row should be gone) — still OK
            # only if secret_ref empty or matches.
        secrets.delete_camera_secret(ref)
        return
    raise ValueError(f"unknown outbox op {row.op}")


def process_outbox_row(
    secrets: SecretsStore,
    session_factory,
    row_id: int,
    *,
    force_retry: bool = False,
) -> str:
    """Process one committed outbox row under camera locks. Returns final status."""
    with session_factory() as db:
        row = db.get(SecretFsOutbox, row_id)
        if row is None:
            return "missing"
        if row.status == STATUS_DONE:
            return STATUS_DONE
        if row.status == STATUS_ABANDONED:
            return STATUS_ABANDONED
        max_attempts = int(row.max_attempts or MAX_ATTEMPTS_DEFAULT)
        if (
            row.status == STATUS_FAILED
            and not force_retry
            and int(row.attempts or 0) >= max_attempts
        ):
            return STATUS_FAILED
        if force_retry and row.status == STATUS_FAILED:
            row.attempts = 0
            row.status = STATUS_PENDING
            row.last_error = ""
            row.updated_at = _utc_now()
            db.flush()
        if _is_stale(db, row):
            row.status = STATUS_ABANDONED
            row.last_error = "stale_generation_or_lifecycle"
            row.updated_at = _utc_now()
            staged_left = row.staged_ref
            db.commit()
            if staged_left and ".staged-" in staged_left:
                unregister_active_staged(secrets, staged_left)
                try:
                    secrets.delete_camera_secret(staged_left)
                except Exception:
                    pass
            return STATUS_ABANDONED

        cid = row.camera_id
        if cid is not None:
            CREDENTIAL_LOCKS.acquire(int(cid))
        try:
            with camera_file_lock(secrets, cid):
                # Re-check stale under lock (concurrent newer commit may have landed)
                db.refresh(row)
                if _is_stale(db, row):
                    row.status = STATUS_ABANDONED
                    row.last_error = "stale_generation_or_lifecycle"
                    row.updated_at = _utc_now()
                    staged_left = row.staged_ref
                    db.commit()
                    if staged_left and ".staged-" in staged_left:
                        unregister_active_staged(secrets, staged_left)
                        try:
                            secrets.delete_camera_secret(staged_left)
                        except Exception:
                            pass
                    return STATUS_ABANDONED

                row.status = STATUS_PROCESSING
                row.attempts = int(row.attempts or 0) + 1
                row.updated_at = _utc_now()
                db.commit()

                try:
                    db.refresh(row)
                    _apply_one(secrets, db, row)
                    row.status = STATUS_DONE
                    row.completed_at = _utc_now()
                    row.last_error = ""
                    row.updated_at = _utc_now()
                    db.commit()
                    return STATUS_DONE
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    db.refresh(row)
                    if err in {"STALE_DELETE_REF", "STALE_CAMERA_LIFECYCLE"} or _is_stale(db, row):
                        row.status = STATUS_ABANDONED
                        row.last_error = err or "stale"
                        if row.staged_ref:
                            unregister_active_staged(secrets, row.staged_ref)
                    elif int(row.attempts) >= int(row.max_attempts or MAX_ATTEMPTS_DEFAULT):
                        row.status = STATUS_FAILED
                        row.last_error = err
                    else:
                        row.status = STATUS_PENDING
                        row.last_error = err
                    row.updated_at = _utc_now()
                    db.commit()
                    logger.error("secret_fs_outbox_apply_failed id=%s err=%s", row.public_id, err)
                    return str(row.status)
        finally:
            if cid is not None:
                CREDENTIAL_LOCKS.release(int(cid))


def _session_factory_from_bind(db: Session):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def apply_outbox_after_commit(secrets: SecretsStore, db: Session) -> list[str]:
    """
    After SQL commit succeeded: apply outbox rows inserted in THIS transaction.
    Uses a fresh session for status updates so postcommit failures never rollback intent.
    """
    ids: list[int] = list(db.info.pop(OUTBOX_IDS_KEY, []) or [])
    # Clear in-memory discard markers — commit succeeded, staged must be promoted not discarded
    db.info.pop(SESSION_KEY, None)
    # Release request-held locks before apply so process_outbox_row uses the same
    # per-camera ordering path as startup/retry (and never deadlocks on non-reentry).
    release_session_credential_locks(db)
    if not ids:
        return []

    # SQLite: the request connection must not stay checked-out while outbox workers
    # open new writers — that deadlocks TestClient/single-threaded finalize (C13).
    bind = db.get_bind()
    try:
        db.close()
    except Exception:
        pass
    from sqlalchemy.orm import sessionmaker

    sm = sessionmaker(
        bind=bind, autoflush=False, autocommit=False, expire_on_commit=False
    )
    failures: list[str] = []
    # Process in id order (monotonic with generation for same camera)
    for rid in sorted(ids):
        status = process_outbox_row(secrets, sm, rid)
        if status not in {STATUS_DONE, STATUS_ABANDONED}:
            failures.append(f"outbox_id={rid}:status={status}")
    return failures


def abort_outbox_after_rollback(secrets: SecretsStore, db: Session) -> None:
    """SQL rolled back — outbox rows are gone. Discard only staged blobs from this request."""
    box: list[dict[str, Any]] = list(db.info.pop(SESSION_KEY, []) or [])
    db.info.pop(OUTBOX_IDS_KEY, None)
    for op in box:
        if op.get("op") == "discard_on_rollback":
            ref = str(op.get("ref") or "")
            if ref and ".staged-" in ref:
                unregister_active_staged(secrets, ref)
                try:
                    secrets.delete_camera_secret(ref)
                except Exception:  # noqa: BLE001
                    logger.warning("secret_fs_rollback_discard_failed ref=%s", ref)
    comps: list[Callable[[], None]] = list(db.info.pop(RUNTIME_COMPENSATE_KEY, []) or [])
    for fn in comps:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("runtime_compensate_failed err=%s", exc)
    release_session_credential_locks(db)


def scrub_orphaned_staged_exclusive(
    secrets: SecretsStore,
    session_factory,
    *,
    max_age_sec: int = STAGED_ORPHAN_MAX_AGE_SEC,
) -> int:
    """Age-gated orphan scrub under exclusive maintenance lock — never during in-flight requests.

    Only deletes staged blobs that are:
    - older than max_age_sec, AND
    - not referenced by any open outbox row, AND
    - not covered by an active in-process/durable lease (C11).
    """
    import time

    lock_path = secrets._dir / "_locks" / "staging-maintenance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        try:
            fd.close()
        except Exception:
            pass
        return 0

    try:
        referenced: set[str] = set()
        with session_factory() as db:
            for r in db.scalars(
                select(SecretFsOutbox).where(
                    SecretFsOutbox.status.in_(
                        [STATUS_PENDING, STATUS_PROCESSING, STATUS_FAILED]
                    )
                )
            ).all():
                if r.staged_ref:
                    referenced.add(r.staged_ref)
        now = time.time()
        orphans = 0
        for p in secrets._dir.glob("camera-*.staged-*.bin"):
            if p.name in referenced:
                continue
            if _is_staged_leased(secrets, p.name, max_lease_age_sec=max_age_sec):
                continue
            try:
                age = now - p.stat().st_mtime
            except OSError:
                continue
            if age < max_age_sec:
                continue
            try:
                secrets.delete_camera_secret(p.name)
                unregister_active_staged(secrets, p.name)
                orphans += 1
            except Exception:
                pass
        return orphans
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fd.close()
        except Exception:
            pass


def recover_pending_outbox(
    secrets: SecretsStore,
    session_factory,
    *,
    force_retry: bool = False,
    scrub_orphans: bool = False,
) -> dict[str, Any]:
    """Startup/retry: process only committed pending/failed rows (SQLite proof of commit).

    Does NOT delete in-flight uncommitted staged blobs (C11). Optional exclusive
    age-gated scrub only when scrub_orphans=True (startup maintenance).
    """
    applied = 0
    failed = 0
    abandoned = 0
    errors: list[str] = []
    with session_factory() as db:
        rows = db.scalars(
            select(SecretFsOutbox)
            .where(SecretFsOutbox.status.in_([STATUS_PENDING, STATUS_PROCESSING, STATUS_FAILED]))
            .order_by(
                SecretFsOutbox.camera_id.asc(),
                SecretFsOutbox.generation.asc(),
                SecretFsOutbox.id.asc(),
            )
        ).all()
        ids = [int(r.id) for r in rows]
    for rid in ids:
        status = process_outbox_row(secrets, session_factory, rid, force_retry=force_retry)
        if status == STATUS_DONE:
            applied += 1
        elif status == STATUS_ABANDONED:
            abandoned += 1
        else:
            failed += 1
            errors.append(f"id={rid}:status={status}")

    orphans = 0
    if scrub_orphans:
        orphans = scrub_orphaned_staged_exclusive(secrets, session_factory)

    # Remove legacy JSON journals if present (no longer authoritative)
    legacy = secrets._dir / "_fs_outbox"
    legacy_removed = 0
    if legacy.is_dir():
        for path in legacy.glob("*.json"):
            try:
                path.unlink()
                legacy_removed += 1
            except OSError:
                pass
    return {
        "journals_applied": applied,
        "journals_failed": failed,
        "journals_abandoned": abandoned,
        "orphaned_staged_scrubbed": orphans,
        "legacy_json_removed": legacy_removed,
        "errors": errors[:20],
    }


# Back-compat alias used by older call sites / tests
def recover_pending_journals(secrets: SecretsStore, session_factory=None) -> dict[str, Any]:
    if session_factory is None:
        return {
            "journals_applied": 0,
            "journals_failed": 0,
            "error": "session_factory_required",
        }
    return recover_pending_outbox(secrets, session_factory)


def raise_if_outbox_failures(failures: list[str]) -> None:
    if not failures:
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "SECRET_FS_OUTBOX_INCOMPLETE",
            "message_vi": (
                "Đã lưu DB nhưng cập nhật file credential chưa hoàn tất. "
                "Intent đã commit trong SQLite — dùng retry hoặc khởi động lại dịch vụ."
            ),
            "failures": failures[:10],
            "retriable": True,
        },
    )


def list_pending_outbox(db: Session, *, redact: bool = True) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(SecretFsOutbox)
        .where(SecretFsOutbox.status.in_([STATUS_PENDING, STATUS_PROCESSING, STATUS_FAILED]))
        .order_by(SecretFsOutbox.id.asc())
    ).all()
    out = []
    for r in rows:
        item = {
            "id": r.id,
            "public_id": r.public_id[:8] + "…" if redact else r.public_id,
            "camera_id": r.camera_id,
            "op": r.op,
            "generation": r.generation,
            "status": r.status,
            "attempts": r.attempts,
        }
        if not redact:
            item["last_error"] = r.last_error
            item["staged_ref"] = r.staged_ref
            item["live_ref"] = r.live_ref
        elif r.last_error:
            item["has_error"] = True
        out.append(item)
    return out


# Deprecated stubs — keep import paths from old tests temporarily
def write_durable_journal(secrets: SecretsStore, db: Session) -> Path | None:
    """No-op: commit proof is the SQLite outbox row in the same transaction."""
    return None

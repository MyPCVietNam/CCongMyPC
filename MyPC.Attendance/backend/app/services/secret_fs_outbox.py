"""Per-session + durable filesystem outbox for camera credentials.

P0-01: never use process-global AppState queues (cross-request drain).
Crash consistency: journal ops under secrets/_fs_outbox/ BEFORE SQL commit so a
kill between commit and promote is recoverable on restart.
Concurrency: per-camera locks span stage → commit → promote/delete.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.secrets_store import SecretsStore

logger = logging.getLogger(__name__)

OutboxOp = dict[str, Any]
SESSION_KEY = "secret_fs_ops"
LOCKS_KEY = "credential_locks_held"
JOURNAL_KEY = "secret_fs_journal_id"
RUNTIME_COMPENSATE_KEY = "runtime_compensate"
OUTBOX_SUBDIR = "_fs_outbox"


class CameraCredentialLockTable:
    """Process-local per-camera locks for REPLACE/REMOVE serialization."""

    def __init__(self) -> None:
        self._meta = threading.Lock()
        self._locks: dict[int, threading.Lock] = {}

    def acquire(self, camera_id: int) -> None:
        cid = int(camera_id)
        with self._meta:
            lock = self._locks.setdefault(cid, threading.Lock())
        lock.acquire()

    def release(self, camera_id: int) -> None:
        cid = int(camera_id)
        with self._meta:
            lock = self._locks.get(cid)
        if lock is not None and lock.locked():
            try:
                lock.release()
            except RuntimeError:
                pass


# Module singleton — one table per process
CREDENTIAL_LOCKS = CameraCredentialLockTable()


def session_secret_outbox(db: Session) -> list[OutboxOp]:
    box = db.info.get(SESSION_KEY)
    if box is None:
        box = []
        db.info[SESSION_KEY] = box
    return box  # type: ignore[return-value]


def acquire_camera_credential_lock(db: Session, camera_id: int) -> None:
    """Hold until outbox applied or aborted — prevents concurrent REPLACE races."""
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
    """Run on SQL rollback only — undo in-memory LIVE binds started before commit."""
    db.info.setdefault(RUNTIME_COMPENSATE_KEY, []).append(fn)


def queue_delete(db: Session, secret_ref: str, *, camera_id: int | None = None) -> None:
    if not secret_ref:
        return
    if camera_id is not None:
        acquire_camera_credential_lock(db, camera_id)
    session_secret_outbox(db).append(
        {"op": "delete", "ref": secret_ref, "camera_id": camera_id}
    )


def queue_promote(
    db: Session,
    *,
    staged_ref: str,
    live_ref: str,
    camera_id: int,
) -> None:
    if not staged_ref or not live_ref:
        raise ValueError("staged_ref và live_ref bắt buộc")
    acquire_camera_credential_lock(db, camera_id)
    box = session_secret_outbox(db)
    box.append(
        {
            "op": "promote",
            "staged": staged_ref,
            "live": live_ref,
            "camera_id": int(camera_id),
        }
    )
    box.append({"op": "discard_on_rollback", "ref": staged_ref, "camera_id": int(camera_id)})


def queue_discard_staged(db: Session, staged_ref: str) -> None:
    if staged_ref:
        session_secret_outbox(db).append({"op": "discard_on_rollback", "ref": staged_ref})


def _outbox_dir(secrets: SecretsStore) -> Path:
    d = secrets._dir / OUTBOX_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def write_durable_journal(secrets: SecretsStore, db: Session) -> Path | None:
    """
    Persist pending promote/delete ops BEFORE SQL commit.
    Crash after commit + before apply can replay from this journal.
    """
    box: list[OutboxOp] = list(db.info.get(SESSION_KEY) or [])
    durable = [op for op in box if op.get("op") in {"promote", "delete"}]
    if not durable:
        return None
    jid = uuid.uuid4().hex
    payload = {
        "id": jid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ops": durable,
        "status": "pending",
    }
    path = _outbox_dir(secrets) / f"{jid}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    db.info[JOURNAL_KEY] = jid
    return path


def _apply_ops(secrets: SecretsStore, ops: list[OutboxOp]) -> list[str]:
    failures: list[str] = []
    for op in ops:
        kind = str(op.get("op") or "")
        try:
            if kind == "promote":
                secrets.promote_staged_camera_secret(op["staged"], op["live"])
            elif kind == "delete":
                secrets.delete_camera_secret(op["ref"])
        except Exception as exc:  # noqa: BLE001
            msg = f"{kind}:{op}: {exc}"
            failures.append(msg)
            logger.error("secret_fs_outbox_apply_failed %s", msg)
    return failures


def _rewrite_journal(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def apply_journal_file(secrets: SecretsStore, path: Path) -> list[str]:
    """Apply one durable journal; delete on full success; retain remaining ops on failure."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("secret_fs_journal_corrupt path=%s err=%s", path, exc)
        return [f"corrupt:{path.name}:{exc}"]
    ops = list(payload.get("ops") or [])
    remaining: list[OutboxOp] = []
    failures: list[str] = []
    for op in ops:
        kind = str(op.get("op") or "")
        try:
            if kind == "promote":
                # Idempotent if already promoted (staged missing + live exists)
                staged = op.get("staged") or ""
                live = op.get("live") or ""
                if secrets.has_secret(staged):
                    secrets.promote_staged_camera_secret(staged, live)
                elif not secrets.has_secret(live):
                    raise FileNotFoundError(f"staged and live missing: {staged} / {live}")
            elif kind == "delete":
                secrets.delete_camera_secret(op["ref"])
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            remaining.append(op)
            failures.append(f"{kind}:{op}: {exc}")
            logger.error("secret_fs_journal_op_failed %s", failures[-1])
    if remaining:
        payload["ops"] = remaining
        payload["status"] = "failed"
        payload["last_error"] = failures[-1] if failures else "unknown"
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        _rewrite_journal(path, payload)
        return failures
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return []


def apply_outbox_after_commit(secrets: SecretsStore, db: Session) -> list[str]:
    """
    After durable SQL commit: apply journal (preferred) or in-memory ops.
    Leaves journal on failure for restart/retry — never silent success.
    """
    # Clear in-memory box; durable journal is source of truth post-commit
    box: list[OutboxOp] = list(db.info.pop(SESSION_KEY, []) or [])
    jid = db.info.pop(JOURNAL_KEY, None)
    failures: list[str] = []
    if jid:
        path = _outbox_dir(secrets) / f"{jid}.json"
        failures = apply_journal_file(secrets, path)
    else:
        durable = [op for op in box if op.get("op") in {"promote", "delete"}]
        failures = _apply_ops(secrets, durable)
        if failures:
            # Persist remaining for recovery even if pre-commit journal was skipped
            jid2 = uuid.uuid4().hex
            path = _outbox_dir(secrets) / f"{jid2}.json"
            rem = []
            # Re-queue failed ops approximately (all durable if any failed)
            rem = durable
            _rewrite_journal(
                path,
                {
                    "id": jid2,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "ops": rem,
                    "status": "failed",
                    "last_error": failures[-1],
                },
            )
    release_session_credential_locks(db)
    return failures


def abort_outbox_after_rollback(secrets: SecretsStore, db: Session) -> None:
    """Discard staged files + run runtime compensations — never delete live credentials."""
    box: list[OutboxOp] = list(db.info.pop(SESSION_KEY, []) or [])
    jid = db.info.pop(JOURNAL_KEY, None)
    if jid:
        path = _outbox_dir(secrets) / f"{jid}.json"
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    for op in box:
        if op.get("op") == "discard_on_rollback":
            ref = str(op.get("ref") or "")
            if ref and ".staged-" in ref:
                try:
                    secrets.delete_camera_secret(ref)
                except Exception:  # noqa: BLE001
                    logger.warning("secret_fs_outbox_rollback_discard_failed ref=%s", ref)
    comps: list[Callable[[], None]] = list(db.info.pop(RUNTIME_COMPENSATE_KEY, []) or [])
    for fn in comps:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("runtime_compensate_failed err=%s", exc)
    release_session_credential_locks(db)


def recover_pending_journals(secrets: SecretsStore) -> dict[str, Any]:
    """Startup/retry: replay all durable journals. Returns summary for diagnostics."""
    d = _outbox_dir(secrets)
    applied = 0
    failed = 0
    errors: list[str] = []
    for path in sorted(d.glob("*.json")):
        fails = apply_journal_file(secrets, path)
        if fails:
            failed += 1
            errors.extend(fails)
        else:
            applied += 1
    # Also scrub orphaned staged blobs not referenced by any remaining journal
    referenced: set[str] = set()
    for path in d.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for op in payload.get("ops") or []:
                if op.get("staged"):
                    referenced.add(str(op["staged"]))
        except Exception:
            pass
    orphans = 0
    for p in secrets._dir.glob("camera-*.staged-*.bin"):
        if p.name not in referenced:
            try:
                secrets.delete_camera_secret(p.name)
                orphans += 1
            except Exception:
                pass
    return {
        "journals_applied": applied,
        "journals_failed": failed,
        "orphaned_staged_scrubbed": orphans,
        "errors": errors[:20],
        "pending_dir": str(d),
    }


def raise_if_outbox_failures(failures: list[str]) -> None:
    """Observable failure after SQL commit — never report silent success."""
    if not failures:
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "SECRET_FS_OUTBOX_INCOMPLETE",
            "message_vi": (
                "Đã lưu DB nhưng cập nhật file credential chưa hoàn tất. "
                "Hệ thống đã ghi nhật ký khôi phục — thử lại hoặc khởi động lại dịch vụ."
            ),
            "failures": failures[:10],
            "retriable": True,
        },
    )


def list_pending_journals(secrets: SecretsStore) -> list[dict[str, Any]]:
    out = []
    for path in sorted(_outbox_dir(secrets).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": payload.get("id"),
                    "status": payload.get("status"),
                    "ops_count": len(payload.get("ops") or []),
                    "last_error": payload.get("last_error"),
                    "path": path.name,
                }
            )
        except Exception as exc:  # noqa: BLE001
            out.append({"path": path.name, "status": "corrupt", "last_error": str(exc)})
    return out

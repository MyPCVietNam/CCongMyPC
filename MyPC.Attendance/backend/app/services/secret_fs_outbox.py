"""Per-session filesystem outbox for camera credentials.

Never attach pending deletes/promotes to process-global AppState — an unrelated
request commit must not drain another transaction's work (P0-01 audit).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.secrets_store import SecretsStore

logger = logging.getLogger(__name__)

OutboxOp = dict[str, Any]
SESSION_KEY = "secret_fs_ops"


def session_secret_outbox(db: Session) -> list[OutboxOp]:
    """Return the transaction-owned outbox list for this SQLAlchemy Session."""
    box = db.info.get(SESSION_KEY)
    if box is None:
        box = []
        db.info[SESSION_KEY] = box
    return box  # type: ignore[return-value]


def queue_delete(db: Session, secret_ref: str) -> None:
    if not secret_ref:
        return
    session_secret_outbox(db).append({"op": "delete", "ref": secret_ref})


def queue_promote(db: Session, *, staged_ref: str, live_ref: str) -> None:
    """After commit: atomically replace live with staged. On rollback: discard staged."""
    if not staged_ref or not live_ref:
        raise ValueError("staged_ref và live_ref bắt buộc")
    box = session_secret_outbox(db)
    box.append({"op": "promote", "staged": staged_ref, "live": live_ref})
    box.append({"op": "discard_on_rollback", "ref": staged_ref})


def queue_discard_staged(db: Session, staged_ref: str) -> None:
    if staged_ref:
        session_secret_outbox(db).append({"op": "discard_on_rollback", "ref": staged_ref})


def apply_outbox_after_commit(secrets: SecretsStore, db: Session) -> list[str]:
    """
    Run filesystem side-effects only for THIS session after durable commit.
    Returns list of failure messages (DB already committed — observable/retriable).
    """
    box: list[OutboxOp] = list(db.info.pop(SESSION_KEY, []) or [])
    failures: list[str] = []
    for op in box:
        kind = str(op.get("op") or "")
        if kind == "discard_on_rollback":
            # Rollback-only marker — ignore after successful commit
            continue
        try:
            if kind == "promote":
                secrets.promote_staged_camera_secret(op["staged"], op["live"])
            elif kind == "delete":
                secrets.delete_camera_secret(op["ref"])
        except Exception as exc:  # noqa: BLE001
            msg = f"{kind}:{op}: {exc}"
            failures.append(msg)
            logger.error("secret_fs_outbox_commit_failed %s", msg)
    return failures


def abort_outbox_after_rollback(secrets: SecretsStore, db: Session) -> None:
    """Discard staged files for THIS session only — never delete live credentials."""
    box: list[OutboxOp] = list(db.info.pop(SESSION_KEY, []) or [])
    for op in box:
        if op.get("op") == "discard_on_rollback":
            ref = str(op.get("ref") or "")
            if ref and ".staged-" in ref:
                try:
                    secrets.delete_camera_secret(ref)
                except Exception:  # noqa: BLE001
                    logger.warning("secret_fs_outbox_rollback_discard_failed ref=%s", ref)
        # delete/promote ops for live refs are dropped — live file untouched

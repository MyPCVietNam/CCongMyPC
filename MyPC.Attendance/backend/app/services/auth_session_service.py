"""Durable auth sessions + epoch invalidation (survives process restart)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.utc_time import utc_now
from app.models.entities import AuthSession, User


def create_session(
    db: Session,
    *,
    user: User,
    sid: str,
    max_age_seconds: int,
) -> AuthSession:
    now = utc_now()
    row = AuthSession(
        sid=sid,
        user_id=user.id,
        auth_epoch=int(getattr(user, "auth_epoch", 1) or 1),
        created_at=now,
        expires_at=now + timedelta(seconds=max(60, int(max_age_seconds))),
        revoked=False,
        revoke_reason="",
    )
    db.add(row)
    db.flush()
    return row


def get_valid_session(db: Session, *, sid: str, user: User) -> AuthSession | None:
    row = db.scalar(select(AuthSession).where(AuthSession.sid == sid))
    if row is None or row.revoked or row.user_id != user.id:
        return None
    epoch = int(getattr(user, "auth_epoch", 1) or 1)
    if int(row.auth_epoch or 0) != epoch:
        return None
    now = utc_now()
    exp = row.expires_at
    if exp is not None:
        # SQLite may return naive
        if getattr(exp, "tzinfo", None) is None:
            from datetime import timezone

            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            return None
    return row


def revoke_session(db: Session, *, sid: str, reason: str = "LOGOUT") -> None:
    row = db.scalar(select(AuthSession).where(AuthSession.sid == sid))
    if row is None or row.revoked:
        return
    row.revoked = True
    row.revoke_reason = reason[:64]


def revoke_all_user_sessions(db: Session, *, user_id: int, reason: str) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked.is_(False))
        .values(revoked=True, revoke_reason=reason[:64])
    )
    return int(result.rowcount or 0)


def bump_auth_epoch(db: Session, user: User) -> int:
    current = int(getattr(user, "auth_epoch", 1) or 1)
    user.auth_epoch = current + 1
    db.flush()
    return int(user.auth_epoch)

"""First-run administrator bootstrap — no default password in public source."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.security import generate_bootstrap_password, hash_password
from app.models.entities import User


def ensure_admin(
    session: Session,
    clock: Clock,
    *,
    username: str,
    password: str | None,
) -> tuple[User, str | None]:
    """
    Returns (user, plaintext_password_if_generated).
    Generated password is only returned once at creation for local setup display.
    """
    count = session.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = session.scalar(select(User).limit(1))
        assert user is not None
        return user, None

    plain = password if password else generate_bootstrap_password()
    user = User(
        username=username,
        password_hash=hash_password(plain),
        display_name="Quản trị viên",
        role="SYSTEM_ADMIN",
        permissions_json='["SYSTEM_ADMIN"]',
        active=True,
        created_at=clock.now_utc(),
    )
    session.add(user)
    session.flush()
    return user, plain if not password else None

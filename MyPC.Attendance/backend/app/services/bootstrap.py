"""First-run administrator bootstrap — no default password in public source."""

from __future__ import annotations

import os
import stat
from pathlib import Path

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
    require_password_change: bool = True,
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

    generated = password is None or password == ""
    plain = password if password else generate_bootstrap_password()
    user = User(
        username=username,
        password_hash=hash_password(plain),
        display_name="Quản trị viên",
        role="SYSTEM_ADMIN",
        permissions_json="[]",
        active=True,
        must_change_password=bool(require_password_change and generated),
        created_at=clock.now_utc(),
    )
    session.add(user)
    session.flush()
    return user, plain if generated else None


def write_first_run_secret_file(path: Path, username: str, password: str) -> None:
    """Write bootstrap secret with restrictive permissions; never log contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"username={username}\npassword={password}\n"
        "BẮT BUỘC đổi mật khẩu ngay sau lần đăng nhập đầu.\n"
        "Xóa tệp này sau khi đổi mật khẩu.\n"
    )
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass


def secure_delete_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with path.open("wb") as f:
            f.write(b"\0" * max(size, 1))
            f.flush()
            os.fsync(f.fileno())
        path.unlink(missing_ok=True)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

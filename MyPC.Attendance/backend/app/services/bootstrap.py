"""First-run administrator bootstrap — no default password in public source."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
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
    Existing databases are never silently re-bootstrapped.
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
        auth_epoch=1,
        created_at=clock.now_utc(),
    )
    session.add(user)
    session.flush()
    return user, plain if generated else None


def _apply_windows_restrictive_dacl(path: Path) -> None:
    """Best-effort owner-only ACL on Windows; no-op elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import subprocess

        # icacls: reset then grant current user only (no Everyone / Users)
        user = os.environ.get("USERNAME") or os.getlogin()
        subprocess.run(
            ["icacls", str(path), "/inheritance:r"],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["icacls", str(path), "/grant:r", f"{user}:(R,W)"],
            check=False,
            capture_output=True,
            text=True,
        )
        # Explicitly remove broad principals if present
        for principal in ("Everyone", "Users", "Authenticated Users", "BUILTIN\\Users"):
            subprocess.run(
                ["icacls", str(path), "/remove", principal],
                check=False,
                capture_output=True,
                text=True,
            )
    except Exception:  # noqa: BLE001
        pass


def write_first_run_secret_file(path: Path, username: str, password: str) -> None:
    """Atomic create with restrictive permissions; never log contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        # Refuse to overwrite an existing secret/path — avoid silent credential replace
        raise FileExistsError(f"first-run secret already present at {path.name}")
    content = (
        f"username={username}\npassword={password}\n"
        "BẮT BUỘC đổi mật khẩu ngay sau lần đăng nhập đầu.\n"
        "Xóa tệp này sau khi đổi mật khẩu thành công trong ứng dụng.\n"
        "Mật khẩu gắn với ĐÚNG thư mục dữ liệu này — không dùng hồ sơ khác.\n"
    )
    fd, tmp_name = tempfile.mkstemp(
        prefix=".first_run_",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except OSError:
            pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    _apply_windows_restrictive_dacl(path)


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


def first_run_secret_present(data_dir: Path) -> bool:
    return (data_dir / "FIRST_RUN_ADMIN.txt").is_file()

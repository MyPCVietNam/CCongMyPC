"""Persistent session signing secret — CSPRNG, survive restart, reject weak production keys."""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from app.core.windows_secrets_acl import (
    SecretAccessDeniedError,
    apply_new_secret_file_acl,
    assert_readable_existing_secret,
    prepare_secrets_dir_for_app,
)

KNOWN_WEAK_SECRETS = frozenset(
    {
        "",
        "dev-only-change-me-in-production-32b",
        "change-me",
        "secret",
        "test-secret-key-32-bytes-minimum!!",
    }
)


class WeakSecretError(RuntimeError):
    pass


def is_weak_secret(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    if not v or v in KNOWN_WEAK_SECRETS:
        return True
    if len(v.encode("utf-8")) < 32:
        return True
    return False


def load_or_create_session_secret(
    data_dir: Path,
    *,
    env_value: str | None,
    app_env: str,
    demo_mode: bool,
    allow_ephemeral_dev: bool = False,
) -> str:
    """
    Resolution order:
    1. Explicit MYPC_SECRET_KEY if strong enough (or explicitly allowed for tests).
    2. Persistent file data_dir/secrets/session.secret (created once with CSPRNG).
    3. Production refuses weak/missing; development may create file.

    If session.secret exists but is unreadable → SECRET_ACCESS_DENIED (never regenerate).
    """
    prepare_secrets_dir_for_app(data_dir)
    secrets_dir = data_dir / "secrets"
    path = secrets_dir / "session.secret"

    if env_value:
        if app_env == "production" and not demo_mode and is_weak_secret(env_value):
            raise WeakSecretError(
                "MYPC_SECRET_KEY yếu/mặc định bị từ chối trong production. "
                "Đặt khóa ≥32 bytes entropy hoặc để trống để tạo file cục bộ."
            )
        if not is_weak_secret(env_value) or allow_ephemeral_dev or app_env != "production":
            if not is_weak_secret(env_value) and not path.exists():
                _write_new_secret_text(path, env_value)
            elif path.exists():
                assert_readable_existing_secret(path)
            return env_value

    if path.exists():
        assert_readable_existing_secret(path)
        try:
            stored = path.read_text(encoding="utf-8").strip()
        except PermissionError as exc:
            raise SecretAccessDeniedError(path) from exc
        if is_weak_secret(stored):
            raise WeakSecretError("File session.secret yếu — xoá và khởi tạo lại an toàn.")
        return stored

    if app_env == "production" and not demo_mode and not allow_ephemeral_dev:
        generated = secrets.token_urlsafe(48)
        _write_new_secret_text(path, generated)
        return generated

    generated = secrets.token_urlsafe(48)
    _write_new_secret_text(path, generated)
    return generated


def _write_new_secret_text(path: Path, value: str) -> None:
    if path.exists():
        # Never overwrite an existing secret file via create path
        assert_readable_existing_secret(path)
        raise FileExistsError(path.name)
    path.write_text(value, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    apply_new_secret_file_acl(path)


def sign_approval_payload(secret_key: str, payload: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()


def verify_approval_signature(secret_key: str, payload: str, signature: str) -> bool:
    expected = sign_approval_payload(secret_key, payload)
    return hmac.compare_digest(expected, signature or "")

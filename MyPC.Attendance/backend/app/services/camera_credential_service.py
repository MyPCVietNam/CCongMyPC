"""Explicit camera credential update policy — never wipe secrets with blank password.

Transactional safety (P0-02): REPLACE stages a unique encrypted blob and queues
post-commit promotion; REMOVE queues live deletion after commit. Live camera-{id}.bin
is never overwritten or deleted before the owning SQL transaction commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.secret_fs_outbox import acquire_camera_credential_lock, queue_delete, queue_promote
from app.services.secrets_store import SecretsStore

CredentialAction = Literal["keep", "replace", "remove"]


@dataclass
class CredentialApplyResult:
    secret_ref: str
    username_hint: str
    changed: bool
    action: CredentialAction
    # Staged blob for same-request reads before promote (never log contents)
    staged_ref: str = ""


def safe_rtsp_uri_for_edit(stored: str) -> str:
    """Return scheme://host:port/path with NO userinfo — safe to put in forms."""
    raw = (stored or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.hostname:
        # Already path-like or invalid — do not invent credentials
        if "@" in raw:
            return ""
        return raw
    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{host}{port}{path}"


def apply_camera_credentials(
    secrets: SecretsStore,
    *,
    camera_id: int,
    current_secret_ref: str,
    current_username_hint: str,
    action: CredentialAction,
    username: str,
    password: str,
    db: Session | None = None,
) -> CredentialApplyResult:
    """
    keep: never touch secret store; optionally refresh username_hint if provided without password.
    replace: require username+password; stage new secret (promote after commit when db given).
    remove: queue delete of live secret after commit when db given; never delete pre-commit.
    """
    action = action or "keep"
    username = (username or "").strip()
    password = password or ""
    if hasattr(secrets, "live_camera_ref"):
        live_ref = secrets.live_camera_ref(camera_id)
    else:
        live_ref = f"camera-{int(camera_id)}.bin"

    if action == "remove":
        if current_secret_ref and db is not None:
            queue_delete(db, current_secret_ref, camera_id=camera_id)
        elif current_secret_ref and db is None:
            # Legacy/unit path without session — immediate (tests only)
            secrets.delete_camera_secret(current_secret_ref)
        return CredentialApplyResult(
            secret_ref="", username_hint="", changed=True, action="remove"
        )

    if action == "replace":
        if not username or not password:
            raise ValueError(
                "Thay mật khẩu camera cần cả tên đăng nhập và mật khẩu mới (không để trống)."
            )
        return _stage_replace(
            secrets,
            db=db,
            camera_id=camera_id,
            live_ref=live_ref,
            username=username,
            password=password,
        )

    # keep — blank password MUST NOT overwrite
    if password:
        # Backward-compatible: nonempty password implies replace even if action omitted
        if not username:
            # Prefer existing hint/username from store
            stored = secrets.get_camera_secret(current_secret_ref) if current_secret_ref else None
            username = (stored or {}).get("username") or current_username_hint
        if not username:
            raise ValueError("Cần tên đăng nhập khi đặt mật khẩu camera mới.")
        return _stage_replace(
            secrets,
            db=db,
            camera_id=camera_id,
            live_ref=live_ref,
            username=username,
            password=password,
        )

    hint = current_username_hint
    if username and username != current_username_hint:
        # Update hint only; do not rewrite secret with empty password
        hint = username
        stored = secrets.get_camera_secret(current_secret_ref) if current_secret_ref else None
        if stored and stored.get("password"):
            # Re-encrypt with new username + existing password (explicit username rename)
            return _stage_replace(
                secrets,
                db=db,
                camera_id=camera_id,
                live_ref=live_ref,
                username=username,
                password=stored["password"],
                action_label="keep",
            )
    return CredentialApplyResult(
        secret_ref=current_secret_ref or "",
        username_hint=hint,
        changed=False,
        action="keep",
    )


def _stage_replace(
    secrets: SecretsStore,
    *,
    db: Session | None,
    camera_id: int,
    live_ref: str,
    username: str,
    password: str,
    action_label: CredentialAction = "replace",
) -> CredentialApplyResult:
    if db is None:
        # Unit tests without session — write live immediately
        ref = secrets.put_camera_secret(camera_id, username, password)
        return CredentialApplyResult(
            secret_ref=ref, username_hint=username, changed=True, action=action_label
        )
    acquire_camera_credential_lock(db, camera_id)
    staged = secrets.stage_camera_secret(camera_id, username, password)
    queue_promote(db, staged_ref=staged, live_ref=live_ref, camera_id=camera_id)
    return CredentialApplyResult(
        secret_ref=live_ref,
        username_hint=username,
        changed=True,
        action=action_label,
        staged_ref=staged,
    )

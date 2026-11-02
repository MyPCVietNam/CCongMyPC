"""Explicit camera credential update policy — never wipe secrets with blank password."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from app.services.secrets_store import SecretsStore

CredentialAction = Literal["keep", "replace", "remove"]


@dataclass
class CredentialApplyResult:
    secret_ref: str
    username_hint: str
    changed: bool
    action: CredentialAction


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
) -> CredentialApplyResult:
    """
    keep: never touch secret store; optionally refresh username_hint if provided without password.
    replace: require username+password; write new secret.
    remove: delete secret file and clear ref.
    """
    action = action or "keep"
    username = (username or "").strip()
    password = password or ""

    if action == "remove":
        if current_secret_ref:
            secrets.delete_camera_secret(current_secret_ref)
        return CredentialApplyResult(
            secret_ref="", username_hint="", changed=True, action="remove"
        )

    if action == "replace":
        if not username or not password:
            raise ValueError(
                "Thay mật khẩu camera cần cả tên đăng nhập và mật khẩu mới (không để trống)."
            )
        ref = secrets.put_camera_secret(camera_id, username, password)
        return CredentialApplyResult(
            secret_ref=ref, username_hint=username, changed=True, action="replace"
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
        ref = secrets.put_camera_secret(camera_id, username, password)
        return CredentialApplyResult(
            secret_ref=ref, username_hint=username, changed=True, action="replace"
        )

    hint = current_username_hint
    if username and username != current_username_hint:
        # Update hint only; do not rewrite secret with empty password
        hint = username
        stored = secrets.get_camera_secret(current_secret_ref) if current_secret_ref else None
        if stored and stored.get("password"):
            # Re-encrypt with new username + existing password (explicit username rename)
            ref = secrets.put_camera_secret(camera_id, username, stored["password"])
            return CredentialApplyResult(
                secret_ref=ref, username_hint=username, changed=True, action="keep"
            )
    return CredentialApplyResult(
        secret_ref=current_secret_ref or "",
        username_hint=hint,
        changed=False,
        action="keep",
    )

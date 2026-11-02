"""Authentication routes — session-bound CSRF + durable session revocation."""

from __future__ import annotations

import secrets
import time
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    AppState,
    ensure_csrf,
    get_app_state,
    get_current_user,
    get_db,
    require_csrf,
)
from app.core.permissions import permissions_for_user
from app.core.security import hash_password, issue_session_token, load_session_token, verify_password
from app.models.entities import AuditLog, User
from app.services.auth_session_service import (
    bump_auth_epoch,
    create_session,
    revoke_all_user_sessions,
    revoke_session,
)
from app.core.utc_time import utc_now

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LOGIN_MAX_FAILURES = 8
LOGIN_LOCK_SECONDS = 60


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


def _login_key(request: Request, username: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}|{username.strip().lower()}"


def _check_login_rate(state: AppState, key: str) -> None:
    now = time.monotonic()
    entry = state.login_failures.get(key)
    if entry and entry[1] > now:
        raise HTTPException(
            status_code=429,
            detail="Quá nhiều lần đăng nhập thất bại. Thử lại sau ít phút.",
        )


def _record_login_failure(state: AppState, key: str) -> None:
    now = time.monotonic()
    count, _ = state.login_failures.get(key, (0, 0.0))
    count += 1
    locked_until = now + LOGIN_LOCK_SECONDS if count >= LOGIN_MAX_FAILURES else 0.0
    if count >= LOGIN_MAX_FAILURES:
        count = 0
    state.login_failures[key] = (count, locked_until)


def _clear_login_failures(state: AppState, key: str) -> None:
    state.login_failures.pop(key, None)


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    key = _login_key(request, body.username)
    _check_login_rate(state, key)
    user = db.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
    if user is None or not verify_password(user.password_hash, body.password):
        _record_login_failure(state, key)
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    _clear_login_failures(state, key)

    session_id = secrets.token_urlsafe(24)
    epoch = int(getattr(user, "auth_epoch", 1) or 1)
    create_session(
        db,
        user=user,
        sid=session_id,
        max_age_seconds=state.settings.session_max_age_seconds,
    )
    token = issue_session_token(
        state.settings.secret_key,
        {
            "uid": user.id,
            "username": user.username,
            "role": user.role,
            "sid": session_id,
            "auth_epoch": epoch,
        },
    )
    csrf = ensure_csrf(state, session_id)
    response.set_cookie(
        key="mypc_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=state.settings.session_max_age_seconds,
        path="/",
    )
    must_change = bool(getattr(user, "must_change_password", False))
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "permissions": sorted(permissions_for_user(user)),
            "must_change_password": must_change,
        },
        "csrf_token": csrf,
        "session_id": session_id,
        "must_change_password": must_change,
        "data_dir_hint": str(state.settings.data_dir),
    }


@router.post("/logout")
def logout(
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias="mypc_session")] = None,
) -> dict:
    if session_cookie:
        data = load_session_token(
            state.settings.secret_key,
            session_cookie,
            state.settings.session_max_age_seconds,
        )
        if data and data.get("sid"):
            revoke_session(db, sid=str(data["sid"]), reason="LOGOUT")
            state.csrf_by_session.pop(str(data["sid"]), None)
    response.delete_cookie("mypc_session", path="/")
    return {"ok": True, "message_vi": "Đã đăng xuất"}


@router.get("/me")
def me(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.get(User, user["uid"])
    if row is None:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại")
    sid = str(user.get("sid") or "")
    csrf = state.csrf_by_session.get(sid) or ensure_csrf(state, sid)
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "role": row.role,
        "permissions": sorted(permissions_for_user(row)),
        "must_change_password": bool(getattr(row, "must_change_password", False)),
        "csrf_token": csrf,
        "session_id": sid,
        "app_env": state.settings.app_env,
        "demo_mode": state.settings.demo_mode,
        "data_dir_hint": str(state.settings.data_dir),
    }


@router.get("/profile-status")
def profile_status(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Sanitized first-run / profile diagnostics — never returns secrets."""
    row = db.get(User, user["uid"])
    setup = state.settings.data_dir / "FIRST_RUN_ADMIN.txt"
    return {
        "username": row.username if row else None,
        "must_change_password": bool(row and row.must_change_password),
        "data_dir": str(state.settings.data_dir),
        "first_run_secret_file_present": setup.exists(),
        "note_vi": (
            "Mật khẩu lần đầu gắn với thư mục dữ liệu này. "
            "401 khi đổi mật khẩu nghĩa là mật khẩu hiện tại bị từ chối — "
            "chưa áp dụng mật khẩu mới. Không in nội dung tệp bí mật."
        ),
        "secrets_redacted": True,
    }


@router.post("/change-password", dependencies=[Depends(require_csrf)])
def change_password(
    body: ChangePasswordBody,
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = db.get(User, user["uid"])
    if row is None or not verify_password(row.password_hash, body.current_password):
        raise HTTPException(status_code=401, detail="Mật khẩu hiện tại không đúng")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="Mật khẩu mới phải khác mật khẩu cũ")
    if len(body.new_password) < 10:
        raise HTTPException(status_code=422, detail="Mật khẩu mới phải có ít nhất 10 ký tự")

    row.password_hash = hash_password(body.new_password)
    row.must_change_password = False
    new_epoch = bump_auth_epoch(db, row)
    revoked = revoke_all_user_sessions(db, user_id=row.id, reason="PASSWORD_CHANGE")
    db.add(
        AuditLog(
            actor=row.username,
            action="PASSWORD_CHANGE",
            entity_type="user",
            entity_id=str(row.id),
            before_checksum="",
            after_checksum=f"auth_epoch={new_epoch}",
            reason=f"sessions_revoked={revoked}; secrets_redacted=true",
            timestamp=utc_now(),
            request_id=str(user.get("sid") or "")[:64],
        )
    )
    db.flush()
    sid = str(user.get("sid") or "")
    state.csrf_by_session.pop(sid, None)
    # Drop any CSRF entries for this user (best-effort in-memory map)
    for k in list(state.csrf_by_session.keys()):
        if k == sid:
            state.csrf_by_session.pop(k, None)
    response.delete_cookie("mypc_session", path="/")
    # Cleanup first-run file only after successful DB commit (get_db commits after return)
    state.pending_secret_cleanup = str(state.settings.data_dir / "FIRST_RUN_ADMIN.txt")  # type: ignore[attr-defined]
    return {
        "ok": True,
        "message_vi": (
            "Đã đổi mật khẩu. Phiên cũ đã thu hồi — vui lòng đăng nhập lại bằng mật khẩu mới."
        ),
        "must_relogin": True,
    }

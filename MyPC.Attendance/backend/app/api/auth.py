"""Authentication routes — session-bound CSRF."""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
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
from app.core.security import hash_password, issue_session_token, verify_password
from app.models.entities import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/login")
def login(
    body: LoginBody,
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    session_id = secrets.token_urlsafe(24)
    token = issue_session_token(
        state.settings.secret_key,
        {
            "uid": user.id,
            "username": user.username,
            "role": user.role,
            "sid": session_id,
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
    }


@router.post("/logout")
def logout(response: Response) -> dict:
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
    row.password_hash = hash_password(body.new_password)
    row.must_change_password = False
    db.flush()
    sid = str(user.get("sid") or "")
    state.csrf_by_session.pop(sid, None)
    response.delete_cookie("mypc_session", path="/")
    setup_path = state.settings.data_dir / "FIRST_RUN_ADMIN.txt"
    if setup_path.exists():
        try:
            setup_path.write_bytes(b"\0" * max(setup_path.stat().st_size, 1))
            setup_path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "message_vi": "Đã đổi mật khẩu. Vui lòng đăng nhập lại."}

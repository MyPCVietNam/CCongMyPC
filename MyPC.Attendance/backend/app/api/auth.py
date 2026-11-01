"""Authentication routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AppState, ensure_csrf, get_app_state, get_current_user, get_db
from app.core.security import issue_session_token, verify_password
from app.models.entities import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


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

    token = issue_session_token(
        state.settings.secret_key,
        {"uid": user.id, "username": user.username, "role": user.role},
    )
    csrf = ensure_csrf(state, user.id)
    response.set_cookie(
        key="mypc_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=state.settings.session_max_age_seconds,
        path="/",
    )
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
        "csrf_token": csrf,
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
    csrf = state.csrf_by_session.get(str(row.id)) or ensure_csrf(state, row.id)
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "role": row.role,
        "csrf_token": csrf,
    }

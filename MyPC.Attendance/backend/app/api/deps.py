"""FastAPI dependencies and application state."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.permissions import permissions_for_user
from app.core.security import load_session_token, new_csrf_token
from app.core.settings import AppSettings
from app.models.entities import User
from app.services.attendance_service import AttendanceService
from app.services.config_service import ConfigService
from app.services.secrets_store import SecretsStore
from app.vision.mock_camera import MockCameraGateway


@dataclass
class AppState:
    settings: AppSettings
    clock: Clock
    session_factory: sessionmaker[Session]
    config_service: ConfigService
    attendance_service: AttendanceService
    secrets: SecretsStore
    camera: MockCameraGateway
    bootstrap_password_once: str | None = None
    # CSRF bound to session_id (not bare user id) — concurrent browsers keep independent tokens
    csrf_by_session: dict[str, str] = field(default_factory=dict)
    face_pipeline: Any = None
    template_store: Any = None
    enrollment_service: Any = None
    auto_enrollment_service: Any = None
    camera_gateway: Any = None  # legacy singleton pointer
    camera_registry: Any = None  # CameraSourceRegistry — per-camera LIVE/REPLAY/MOCK


def get_app_state(request: Request) -> AppState:
    return request.app.state.container


def get_db(state: Annotated[AppState, Depends(get_app_state)]):
    db = state.session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(
    state: Annotated[AppState, Depends(get_app_state)],
    session: Annotated[str | None, Cookie(alias="mypc_session")] = None,
) -> dict[str, Any]:
    if not session:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    data = load_session_token(
        state.settings.secret_key, session, state.settings.session_max_age_seconds
    )
    if not data or "uid" not in data or "sid" not in data:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn")
    return data


def require_csrf(
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    sid = str(user.get("sid") or "")
    expected = state.csrf_by_session.get(sid)
    if not expected or not x_csrf_token or not secrets.compare_digest(expected, x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token không hợp lệ")


def ensure_csrf(state: AppState, session_id: str) -> str:
    token = new_csrf_token()
    state.csrf_by_session[session_id] = token
    return token


def get_user_row(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    row = db.get(User, user["uid"])
    if row is None or not row.active:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại")
    return row


def require_permission(permission: str) -> Callable:
    def _checker(
        user_row: Annotated[User, Depends(get_user_row)],
    ) -> User:
        perms = permissions_for_user(user_row)
        if permission not in perms:
            raise HTTPException(
                status_code=403,
                detail=f"Không có quyền thực hiện thao tác này ({permission})",
            )
        return user_row

    return _checker

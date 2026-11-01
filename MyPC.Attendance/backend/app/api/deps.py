"""FastAPI dependencies and application state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock, SystemClock
from app.core.security import load_session_token, new_csrf_token
from app.core.settings import AppSettings
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
    csrf_by_session: dict[str, str] = field(default_factory=dict)


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
    request: Request,
    state: Annotated[AppState, Depends(get_app_state)],
    session: Annotated[str | None, Cookie(alias="mypc_session")] = None,
) -> dict[str, Any]:
    if not session:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    data = load_session_token(
        state.settings.secret_key, session, state.settings.session_max_age_seconds
    )
    if not data:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn")
    return data


def require_csrf(
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    sid = str(user.get("uid"))
    expected = state.csrf_by_session.get(sid)
    if not expected or not x_csrf_token or x_csrf_token != expected:
        raise HTTPException(status_code=403, detail="CSRF token không hợp lệ")


def ensure_csrf(state: AppState, user_id: int) -> str:
    token = new_csrf_token()
    state.csrf_by_session[str(user_id)] = token
    return token

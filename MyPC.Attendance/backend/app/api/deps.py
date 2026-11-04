"""FastAPI dependencies and application state."""

from __future__ import annotations

import logging
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
from app.services.auth_session_service import get_valid_session
from app.services.config_service import ConfigService
from app.services.secrets_store import SecretsStore
from app.vision.mock_camera import MockCameraGateway

logger = logging.getLogger(__name__)

# Routes reachable while must_change_password is true (fail-closed elsewhere).
PASSWORD_CHANGE_ALLOWLIST_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/profile-status",
    "/api/v1/health",
    "/api/v1/system/diagnostics",
    "/api/v1/system/runtime-badge",
)


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
    # Soft rate limit: username/ip -> (fail_count, locked_until_mono)
    login_failures: dict[str, tuple[int, float]] = field(default_factory=dict)
    pending_secret_cleanup: str | None = None
    # NOTE: camera credential FS ops use SQLite SecretFsOutbox (commit-proven), never
    # process-global lists or pre-commit JSON journals (P0 audit 2026-11-03).
    face_pipeline: Any = None
    template_store: Any = None
    enrollment_service: Any = None
    auto_enrollment_service: Any = None
    camera_gateway: Any = None  # legacy singleton pointer
    camera_registry: Any = None  # CameraSourceRegistry — per-camera LIVE/REPLAY/MOCK
    face_detect_preview: Any = None  # LiveFaceDetectPreviewService — shared AI overlay cache
    alembic_ok: bool = True
    alembic_error: str | None = None


def get_app_state(request: Request) -> AppState:
    return request.app.state.container


def get_db(
    request: Request,
    state: Annotated[AppState, Depends(get_app_state)],
):
    """Request-scoped session.

    Commit/outbox apply runs in after-yield on the *same worker thread* as sync
    routes (credential RLock safety). Postcommit HTTPException is recorded on
    request.state; DbSessionFinalizeMiddleware emits the real 503 body (C13).
    """
    from fastapi import HTTPException

    from app.api.db_finalize_middleware import finalize_request_db
    from app.services.secret_fs_outbox import abort_outbox_after_rollback

    db = state.session_factory()
    # Attach for ASGI send-wrapper (scope.state) + worker-thread finalize
    request.state.db_session = db
    request.state.app_state_for_db = state
    request.state.db_finalized = False
    request.state.db_http_error = None
    try:
        yield db
    except Exception:
        if not getattr(request.state, "db_finalized", False):
            try:
                db.rollback()
            except Exception:
                pass
            abort_outbox_after_rollback(state.secrets, db)
            request.state.db_finalized = True
        raise
    else:
        # Same thread as sync endpoint body — safe for CREDENTIAL_LOCKS / flock.
        try:
            finalize_request_db(request.scope["state"])
        except HTTPException as exc:
            request.state.db_http_error = exc
            # Do not re-raise: response may already be serialized; middleware swaps status.
        except Exception as exc:  # noqa: BLE001
            logger.exception("db_finalize_unexpected")
            request.state.db_http_error = HTTPException(
                status_code=503,
                detail={
                    "code": "DB_FINALIZE_ERROR",
                    "message_vi": "Lỗi hoàn tất giao dịch DB.",
                    "retriable": True,
                },
            )
            _ = exc
    # Session closed by DbSessionFinalizeMiddleware.finally


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
    if not data or "uid" not in data or "sid" not in data:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn")
    with state.session_factory() as db:
        row = db.get(User, data["uid"])
        if row is None or not row.active:
            raise HTTPException(
                status_code=401, detail="Người dùng không tồn tại hoặc đã bị vô hiệu"
            )
        # Live role / auth epoch — reject stale privilege or pre-password-change cookies
        token_epoch = int(data.get("auth_epoch") or 0)
        live_epoch = int(getattr(row, "auth_epoch", 1) or 1)
        if token_epoch != live_epoch:
            raise HTTPException(
                status_code=401,
                detail="Phiên đã hết hiệu lực (mật khẩu/khôi phục đã đổi). Đăng nhập lại.",
            )
        if str(data.get("role") or "") != str(row.role or ""):
            raise HTTPException(
                status_code=401,
                detail="Vai trò đã thay đổi — phiên cũ không còn hiệu lực.",
            )
        sid = str(data["sid"])
        if get_valid_session(db, sid=sid, user=row) is None:
            raise HTTPException(
                status_code=401,
                detail="Phiên đã bị thu hồi hoặc hết hạn. Đăng nhập lại.",
            )
        must_change = bool(getattr(row, "must_change_password", False))
        data = {
            **data,
            "uid": row.id,
            "username": row.username,
            "role": row.role,
            "sid": sid,
            "auth_epoch": live_epoch,
            "must_change_password": must_change,
        }
    if must_change and not path_allows_pending_password_change(request.url.path):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "MUST_CHANGE_PASSWORD",
                "message_vi": (
                    "Bắt buộc đổi mật khẩu trước khi dùng chức năng nghiệp vụ. "
                    "Chỉ được truy cập đổi mật khẩu / đăng xuất."
                ),
            },
        )
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


def require_full_access(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Block business APIs until forced password change is complete."""
    if user.get("must_change_password"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "MUST_CHANGE_PASSWORD",
                "message_vi": (
                    "Bắt buộc đổi mật khẩu trước khi dùng chức năng nghiệp vụ. "
                    "Chỉ được truy cập đổi mật khẩu / đăng xuất."
                ),
            },
        )
    return user


def require_permission(permission: str) -> Callable:
    def _checker(
        user: Annotated[dict[str, Any], Depends(require_full_access)],
        user_row: Annotated[User, Depends(get_user_row)],
    ) -> User:
        _ = user
        perms = permissions_for_user(user_row)
        if permission not in perms:
            raise HTTPException(
                status_code=403,
                detail=f"Không có quyền thực hiện thao tác này ({permission})",
            )
        return user_row

    return _checker


def path_allows_pending_password_change(path: str) -> bool:
    p = path.split("?", 1)[0]
    if p in {"/", "/api/docs", "/openapi.json"}:
        return True
    if p.startswith("/assets/"):
        return True
    for prefix in PASSWORD_CHANGE_ALLOWLIST_PREFIXES:
        if p == prefix or p.startswith(prefix + "/"):
            return True
    # SPA deep links are HTML — browser can load shell; APIs still blocked
    if not p.startswith("/api/"):
        return True
    return False

"""Finalize SQL+outbox on the endpoint worker thread; emit real HTTP 503 (C13).

Sync FastAPI routes run in a threadpool. Credential locks are acquired there, so
commit/apply must also run on that same thread (get_db after-yield). Raising
HTTPException during yield-cleanup can race "response already started"; instead
we record the error on request.state and the ASGI send wrapper replaces the
status/body with 503 SECRET_FS_OUTBOX_INCOMPLETE before http.response.start.
"""

from __future__ import annotations

import json
import logging
from typing import Any, MutableMapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def finalize_request_db(scope_state: MutableMapping[str, Any]) -> None:
    """Commit + apply outbox. Idempotent. Runs on the get_db worker thread."""
    if scope_state.get("db_finalized"):
        return
    db = scope_state.get("db_session")
    state = scope_state.get("app_state_for_db")
    if db is None or state is None:
        scope_state["db_finalized"] = True
        return

    from fastapi import HTTPException

    from app.services.secret_fs_outbox import (
        abort_outbox_after_rollback,
        apply_outbox_after_commit,
        raise_if_outbox_failures,
    )

    scope_state["db_finalized"] = True
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        abort_outbox_after_rollback(state.secrets, db)
        raise

    cleanup_error: Exception | None = None
    pending = getattr(state, "pending_secret_cleanup", None)
    if pending:
        from pathlib import Path

        from app.services.bootstrap import secure_delete_file

        try:
            secure_delete_file(Path(str(pending)))
        except Exception as exc:  # noqa: BLE001
            cleanup_error = exc
            logger.error("pending_secret_cleanup_failed err=%s", exc)
        finally:
            state.pending_secret_cleanup = None  # type: ignore[attr-defined]

    failures = apply_outbox_after_commit(state.secrets, db)
    raise_if_outbox_failures(failures)
    if cleanup_error is not None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "POSTCOMMIT_CLEANUP_FAILED",
                "message_vi": "DB đã commit nhưng dọn file bootstrap thất bại — kiểm tra logs.",
                "retriable": True,
            },
        ) from cleanup_error


class DbSessionFinalizeMiddleware:
    """Replace success response with recorded postcommit HTTPException (if any)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state_map: MutableMapping[str, Any] = scope.setdefault("state", {})  # type: ignore[assignment]

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                err = state_map.get("db_http_error")
                if err is not None and not state_map.get("db_response_replaced"):
                    detail = getattr(err, "detail", {"code": "DB_FINALIZE_ERROR"})
                    status = int(getattr(err, "status_code", 503) or 503)
                    body = json.dumps({"detail": detail}).encode("utf-8")
                    headers = [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ]
                    state_map["db_response_replaced"] = True
                    await send(
                        {"type": "http.response.start", "status": status, "headers": headers}
                    )
                    await send({"type": "http.response.body", "body": body})
                    return
            if state_map.get("db_response_replaced"):
                return
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            db = state_map.get("db_session")
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
                state_map["db_session"] = None

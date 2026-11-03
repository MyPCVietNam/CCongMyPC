"""Version-resilient DB finalization before the HTTP response is returned (C13).

FastAPI >=0.118 runs yield-dependency teardown *after* the response is sent, so
get_db after-yield alone cannot flip a 200 into 503. Finalizing inside the route
handler (while the dependency may still be open) — and always honoring a recorded
db_http_error — works on both 0.115.x and newer runtimes.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.db_finalize_middleware import finalize_request_db

logger = logging.getLogger(__name__)


def _success_status(response: Response) -> bool:
    try:
        code = int(getattr(response, "status_code", 200) or 200)
    except (TypeError, ValueError):
        code = 200
    return 200 <= code < 300


def _error_response(err: HTTPException) -> JSONResponse:
    detail = getattr(err, "detail", {"code": "DB_FINALIZE_ERROR"})
    status = int(getattr(err, "status_code", 503) or 503)
    return JSONResponse(status_code=status, content={"detail": detail})


class FinalizingAPIRoute(APIRoute):
    """Finalize commit/outbox after the endpoint returns, before ASGI send."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            response = await original(request)
            state_map = request.scope.setdefault("state", {})

            # Path A: get_db after-yield already finalized and recorded an error
            # (FastAPI 0.115.x timing). Replace success responses here.
            err = state_map.get("db_http_error")
            if err is not None and _success_status(response):
                return _error_response(err)

            # Path B: after-yield not run yet (FastAPI >=0.118). Finalize now.
            if state_map.get("db_session") is not None and not state_map.get("db_finalized"):
                try:
                    finalize_request_db(state_map)
                except HTTPException as exc:
                    state_map["db_http_error"] = exc
                    if _success_status(response):
                        return _error_response(exc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("db_finalize_route_unexpected")
                    wrapped = HTTPException(
                        status_code=503,
                        detail={
                            "code": "DB_FINALIZE_ERROR",
                            "message_vi": "Lỗi hoàn tất giao dịch DB.",
                            "retriable": True,
                        },
                    )
                    state_map["db_http_error"] = wrapped
                    _ = exc
                    if _success_status(response):
                        return _error_response(wrapped)

            return response

        return custom_handler

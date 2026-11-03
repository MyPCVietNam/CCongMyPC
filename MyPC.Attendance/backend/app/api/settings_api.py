"""Live settings draft / apply / history."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from app.api.db_finalize_route import FinalizingAPIRoute
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    AppState,
    get_app_state,
    get_current_user,
    get_db,
    require_csrf,
    require_permission,
)
from app.core.permissions import SETTINGS_APPLY
from app.core.settings import OperationalConfig
from app.models.entities import ConfigRevision, User
from app.services.config_service import ConfigConflictError

router = APIRouter(prefix="/api/v1/settings", tags=["settings"], route_class=FinalizingAPIRoute)


class ApplyBody(BaseModel):
    expected_version: int
    config: OperationalConfig
    reason: str = ""
    simulate_ack_failure: bool = False


@router.get("")
def get_settings(
    state: Annotated[AppState, Depends(get_app_state)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    cfg = state.config_service.active
    return {
        "config": cfg.model_dump(),
        "ack_at": state.config_service.ack_at.isoformat() if state.config_service.ack_at else None,
        "impact_preview_vi": cfg.impact_summary_vi(),
        "labels_vi": {
            "save_draft": "Lưu bản nháp",
            "apply": "Áp dụng",
            "revert": "Khôi phục thay đổi",
            "history": "Lịch sử cấu hình",
        },
    }


@router.post("/draft", dependencies=[Depends(require_csrf)])
def save_draft(
    body: ApplyBody,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    _: Annotated[User, Depends(require_permission(SETTINGS_APPLY))],
) -> dict:
    try:
        rev = state.config_service.save_draft(
            db,
            body.config,
            actor=user.get("username", ""),
            expected_version=body.expected_version,
            reason=body.reason or "draft",
        )
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "draft_version_row": rev.version, "status": "DRAFT", "message_vi": "Đã lưu bản nháp"}


@router.post("/apply", dependencies=[Depends(require_csrf)])
def apply_settings(
    body: ApplyBody,
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[AppState, Depends(get_app_state)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    _: Annotated[User, Depends(require_permission(SETTINGS_APPLY))],
) -> dict:
    try:
        cfg, ok, msg = state.config_service.apply(
            db,
            actor=user.get("username", ""),
            expected_version=body.expected_version,
            payload=body.config,
            reason=body.reason or "apply",
            simulate_ack_failure=body.simulate_ack_failure,
        )
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "ok": ok,
        "applied": ok,
        "message_vi": msg,
        "config_version": cfg.version,
        "ack_at": state.config_service.ack_at.isoformat() if ok and state.config_service.ack_at else None,
        "impact_preview_vi": cfg.impact_summary_vi(),
        "ui_status_vi": "Đã áp dụng" if ok else "Đang chờ áp dụng",
    }


@router.get("/history")
def history(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict]:
    rows = db.scalars(select(ConfigRevision).order_by(ConfigRevision.version.desc()).limit(50)).all()
    return [
        {
            "version": r.version,
            "status": r.status,
            "applied_by": r.applied_by,
            "reason": r.reason,
            "effective_at": r.effective_at.isoformat(),
            "active_ack_at": r.active_ack_at.isoformat() if r.active_ack_at else None,
            "checksum": r.checksum,
        }
        for r in rows
    ]

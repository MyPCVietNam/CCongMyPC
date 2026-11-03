"""Leave requests — TIMEKEEPER_APPROVE enforced server-side."""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from app.api.db_finalize_route import FinalizingAPIRoute
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_csrf
from app.core.clock import SystemClock
from app.models.entities import LeaveRequest, User

router = APIRouter(prefix="/api/v1/leave", tags=["leave"], route_class=FinalizingAPIRoute)

TIMEKEEPER_APPROVE = "TIMEKEEPER_APPROVE"


class LeaveIn(BaseModel):
    employee_id: int
    kind: str = Field(pattern="^(FULL_DAY|MORNING|AFTERNOON|HOURLY|OFFSITE)$")
    work_date: date
    reason: str = ""


def _perms(user_row: User) -> set[str]:
    try:
        raw = json.loads(user_row.permissions_json or "[]")
        return set(raw) | {user_row.role}
    except json.JSONDecodeError:
        return {user_row.role}


@router.get("")
def list_leave(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict]:
    rows = db.scalars(select(LeaveRequest).order_by(LeaveRequest.id.desc())).all()
    return [_out(r) for r in rows]


@router.post("", dependencies=[Depends(require_csrf)])
def submit_leave(
    body: LeaveIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    row = LeaveRequest(
        employee_id=body.employee_id,
        kind=body.kind,
        work_date=body.work_date,
        status="PENDING_APPROVAL",
        reason=body.reason,
        created_by_user_id=user["uid"],
        created_at=SystemClock().now_utc(),
    )
    db.add(row)
    db.flush()
    return _out(row)


@router.post("/{leave_id}/approve", dependencies=[Depends(require_csrf)])
def approve(
    leave_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    actor = db.get(User, user["uid"])
    if actor is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    perms = _perms(actor)
    # SYSTEM_ADMIN does NOT automatically have TIMEKEEPER_APPROVE
    if TIMEKEEPER_APPROVE not in perms:
        raise HTTPException(
            status_code=403,
            detail="Chỉ người phụ trách tính công được xác nhận",
        )
    row = db.get(LeaveRequest, leave_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    # Prevent self-approval when linked to same employee
    if actor.employee_id is not None and actor.employee_id == row.employee_id:
        raise HTTPException(status_code=403, detail="Không được tự phê duyệt đơn của mình")
    row.status = "APPROVED"
    row.decided_by_user_id = actor.id
    row.decided_at = SystemClock().now_utc()
    db.flush()
    return _out(row)


@router.post("/{leave_id}/reject", dependencies=[Depends(require_csrf)])
def reject(
    leave_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    actor = db.get(User, user["uid"])
    if actor is None or TIMEKEEPER_APPROVE not in _perms(actor):
        raise HTTPException(
            status_code=403,
            detail="Chỉ người phụ trách tính công được xác nhận",
        )
    row = db.get(LeaveRequest, leave_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    row.status = "REJECTED"
    row.decided_by_user_id = actor.id
    row.decided_at = SystemClock().now_utc()
    db.flush()
    return _out(row)


def _out(r: LeaveRequest) -> dict:
    return {
        "id": r.id,
        "employee_id": r.employee_id,
        "kind": r.kind,
        "work_date": r.work_date.isoformat(),
        "status": r.status,
        "reason": r.reason,
        "created_by_user_id": r.created_by_user_id,
        "decided_by_user_id": r.decided_by_user_id,
    }

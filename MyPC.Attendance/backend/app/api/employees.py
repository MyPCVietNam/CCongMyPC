"""Employee registry — P00 CRUD subset."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_csrf
from app.core.clock import SystemClock
from app.models.entities import Employee

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


class EmployeeIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=255)
    department: str = ""
    job_title: str = ""
    active: bool = True
    shift_id: str = "MYPC-ADMIN-01"
    biometric_eligible: bool = False


class EmployeeOut(BaseModel):
    id: int
    code: str
    full_name: str
    department: str
    job_title: str
    active: bool
    shift_id: str
    biometric_eligible: bool


@router.get("")
def list_employees(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[EmployeeOut]:
    rows = db.scalars(select(Employee).order_by(Employee.code)).all()
    return [
        EmployeeOut(
            id=r.id,
            code=r.code,
            full_name=r.full_name,
            department=r.department,
            job_title=r.job_title,
            active=r.active,
            shift_id=r.shift_id,
            biometric_eligible=r.biometric_eligible,
        )
        for r in rows
    ]


@router.post("", dependencies=[Depends(require_csrf)])
def create_employee(
    body: EmployeeIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeOut:
    exists = db.scalar(select(Employee).where(Employee.code == body.code))
    if exists:
        raise HTTPException(status_code=409, detail="Mã nhân viên đã tồn tại")
    now = SystemClock().now_utc()
    row = Employee(
        code=body.code,
        full_name=body.full_name,
        department=body.department,
        job_title=body.job_title,
        active=body.active,
        shift_id=body.shift_id,
        biometric_eligible=body.biometric_eligible,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return EmployeeOut(
        id=row.id,
        code=row.code,
        full_name=row.full_name,
        department=row.department,
        job_title=row.job_title,
        active=row.active,
        shift_id=row.shift_id,
        biometric_eligible=row.biometric_eligible,
    )


@router.patch("/{employee_id}", dependencies=[Depends(require_csrf)])
def patch_employee(
    employee_id: int,
    body: EmployeeIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeOut:
    row = db.get(Employee, employee_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    row.code = body.code
    row.full_name = body.full_name
    row.department = body.department
    row.job_title = body.job_title
    row.active = body.active
    row.shift_id = body.shift_id
    row.biometric_eligible = body.biometric_eligible
    row.updated_at = SystemClock().now_utc()
    db.flush()
    return EmployeeOut(
        id=row.id,
        code=row.code,
        full_name=row.full_name,
        department=row.department,
        job_title=row.job_title,
        active=row.active,
        shift_id=row.shift_id,
        biometric_eligible=row.biometric_eligible,
    )

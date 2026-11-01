"""Minimal P00 schema — expandable in later phases."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(128), default="")
    job_title: Mapped[str] = mapped_column(String(128), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    shift_id: Mapped[str] = mapped_column(String(64), default="MYPC-ADMIN-01")
    biometric_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(64), default="SYSTEM_ADMIN")
    permissions_json: Mapped[str] = mapped_column(Text, default="[]")
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CameraDevice(Base):
    __tablename__ = "camera_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), default="EZVIZ H8 Pro")
    host: Mapped[str] = mapped_column(String(255), default="")
    model: Mapped[str] = mapped_column(String(128), default="CS-H8-R100-1J5WKFL")
    firmware: Mapped[str] = mapped_column(String(128), default="")
    # secret_ref points to encrypted local secret store path/key id — never store plaintext
    secret_ref: Mapped[str] = mapped_column(String(255), default="")
    rtsp_url_override: Mapped[str] = mapped_column(String(512), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mock_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    configured_stream: Mapped[str] = mapped_column(String(128), default="")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_status: Mapped[str] = mapped_column(String(64), default="CHUA_CAU_HINH")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecognitionRegion(Base):
    __tablename__ = "recognition_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="arrival")
    # normalized 0..1 rectangle: x,y,w,h JSON
    norm_rect_json: Mapped[str] = mapped_column(Text, default='{"x":0.3,"y":0.05,"w":0.4,"h":0.25}')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    calibration_version: Mapped[int] = mapped_column(Integer, default=1)
    exit_calibration_valid: Mapped[bool] = mapped_column(Boolean, default=False)


class RawObservation(Base):
    __tablename__ = "raw_observations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_raw_observation_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("camera_devices.id"), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    captured_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clock_trust: Mapped[str] = mapped_column(String(32), default="TRUSTED")
    obs_type: Mapped[str] = mapped_column(String(64), default="FACE_MATCH")
    source: Mapped[str] = mapped_column(String(64), default="MOCK")
    quality: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    immutable_metadata: Mapped[str] = mapped_column(Text, default="{}")


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "work_date",
            "window_id",
            "event_type",
            name="uq_attendance_event",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    window_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # MUST be real observed timestamp or null — never forced to 18:00
    observed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_observations.id"), nullable=True
    )
    recognition_version: Mapped[str] = mapped_column(String(64), default="")
    selection_status: Mapped[str] = mapped_column(String(64), default="")
    selection_policy_version: Mapped[str] = mapped_column(String(64), default="")
    evidence_ref: Mapped[str] = mapped_column(String(255), default="")
    photo_captured_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_observed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), default="RULES_ENGINE")
    status: Mapped[str] = mapped_column(String(64), default="RECORDED")
    leave_exemption_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    note_vi: Mapped[str] = mapped_column(Text, default="")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="PENDING_APPROVAL")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConfigRevision(Base):
    __tablename__ = "config_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[str] = mapped_column(String(128), default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    active_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="DRAFT")  # DRAFT|APPLIED|FAILED


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), default="")
    entity_id: Mapped[str] = mapped_column(String(128), default="")
    before_checksum: Mapped[str] = mapped_column(String(128), default="")
    after_checksum: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str] = mapped_column(String(64), default="")

"""Biometric enrollment / encrypted face templates (P01 + P01.5 auto sessions)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BiometricEnrollment(Base):
    __tablename__ = "biometric_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    authorization_ref: Mapped[str] = mapped_column(String(255), default="")
    authorization_ack_vi: Mapped[str] = mapped_column(Text, default="")
    enrolled_by: Mapped[str] = mapped_column(String(128), default="")
    model_id: Mapped[str] = mapped_column(String(128), default="")
    model_hash: Mapped[str] = mapped_column(String(128), default="")
    template_version: Mapped[int] = mapped_column(Integer, default=1)
    # DRAFT|CAPTURING|QUALITY_REVIEW|VALIDATING|ACTIVE|PAUSED|FAILED|CANCELLED|REVOKED
    status: Mapped[str] = mapped_column(String(64), default="DRAFT")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="DEMO")  # DEMO|UPLOAD|REAL_CAMERA|AUTO
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(Text, default="")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("biometric_enrollments.id"), nullable=False)
    encrypted_embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    vector_version: Mapped[str] = mapped_column(String(64), default="sface-2021dec")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_metadata: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    pose_slot: Mapped[str] = mapped_column(String(32), default="")  # FACE_FRONT|FACE_LEFT|FACE_RIGHT


class EnrollmentSession(Base):
    """Guided auto-enrollment session (P01.5). Progress survives restart; ephemeral buffers do not."""

    __tablename__ = "enrollment_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("biometric_enrollments.id"), nullable=False)
    operator: Mapped[str] = mapped_column(String(128), default="")
    # WAITING_FOR_PERSON|CAPTURING|MULTIPLE_PEOPLE|PAUSED|CHECKING_IDENTITY|
    # READY_TO_ACTIVATE|ACTIVE|FAILED|CANCELLED|CAMERA_DISCONNECTED|NEEDS_REVIEW|
    # BODY_CAPTURE_BLOCKED|BLOCKED_BY_CAMERA_GEOMETRY
    status: Mapped[str] = mapped_column(String(64), default="WAITING_FOR_PERSON")
    current_step: Mapped[str] = mapped_column(String(64), default="FACE_FRONT")
    ui_state: Mapped[str] = mapped_column(String(64), default="WAITING_FOR_PERSON")
    guidance_vi: Mapped[str] = mapped_column(Text, default="")
    progress_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="DEMO")
    # Immutable LIVE binding (PR6) — set at start for REAL_CAMERA; frames must match
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bound_profile: Mapped[str] = mapped_column(String(32), default="")
    bound_config_revision: Mapped[str] = mapped_column(String(64), default="")
    camera_lab_approval_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnrollmentSample(Base):
    """Accepted face or body reference sample metadata (images encrypted at rest when retained)."""

    __tablename__ = "enrollment_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("enrollment_sessions.id"), nullable=False, index=True)
    sample_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    slot: Mapped[str] = mapped_column(String(32), nullable=False)  # FACE_* | BODY_*
    kind: Mapped[str] = mapped_column(String(16), default="FACE")  # FACE|BODY_REF
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    native_width: Mapped[int] = mapped_column(Integer, default=0)
    native_height: Mapped[int] = mapped_column(Integer, default=0)
    person_height_px: Mapped[int] = mapped_column(Integer, default=0)
    model_id: Mapped[str] = mapped_column(String(128), default="")
    model_hash: Mapped[str] = mapped_column(String(128), default="")
    frame_hash: Mapped[str] = mapped_column(String(64), default="")  # for duplicate detection
    # Encrypted image blob (AES-GCM); never commit plaintext faces to git
    encrypted_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Encrypted embedding for face samples only
    encrypted_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    replaced: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

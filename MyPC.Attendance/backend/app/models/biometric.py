"""Biometric enrollment / encrypted face templates (P01)."""

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
    status: Mapped[str] = mapped_column(String(64), default="ACTIVE")  # ACTIVE|REVOKED|PENDING_REVIEW
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="DEMO")  # DEMO|UPLOAD|REAL_CAMERA
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(Text, default="")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("biometric_enrollments.id"), nullable=False)
    # AES-GCM ciphertext of float32 embedding vector
    encrypted_embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    vector_version: Mapped[str] = mapped_column(String(64), default="sface-2021dec")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_metadata: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

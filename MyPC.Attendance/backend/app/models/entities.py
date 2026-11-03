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
    # Bumped on password change / recovery — invalidates all prior signed cookies
    auth_epoch: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """Durable session rows — revoke on logout/password change; survives process restart."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    auth_epoch: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoke_reason: Mapped[str] = mapped_column(String(64), default="")


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
    # PR11-HF: soft-delete / archive — preserve historical FK meaning
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    username_hint: Mapped[str] = mapped_column(String(128), default="")
    connection_status: Mapped[str] = mapped_column(String(64), default="UNKNOWN")
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    # Monotonic credential generation — outbox replay must not apply stale ops
    secret_generation: Mapped[int] = mapped_column(Integer, default=0)


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


class CameraStreamProfile(Base):
    """MAIN/SUB stream profile metadata — no raw URI/secrets."""

    __tablename__ = "camera_stream_profiles"
    __table_args__ = (UniqueConstraint("camera_id", "profile", name="uq_camera_stream_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), nullable=False)
    profile: Mapped[str] = mapped_column(String(32), default="MAIN")  # MAIN|SUB|UNKNOWN
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    vendor_max_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor_max_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decoded_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decoded_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str] = mapped_column(String(64), default="")
    fps_measured: Mapped[float | None] = mapped_column(Float, nullable=True)
    health_json: Mapped[str] = mapped_column(Text, default="{}")  # aggregated, no faces/URI
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CameraQualitySettings(Base):
    """Versioned auto-enhance policy per camera — default AUTO_TEST_ONLY."""

    __tablename__ = "camera_quality_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), unique=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    requested_mode: Mapped[str] = mapped_column(String(32), default="AUTO")  # OFF|AUTO
    effective_mode: Mapped[str] = mapped_column(String(32), default="AUTO_TEST_ONLY")
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by: Mapped[str] = mapped_column(String(128), default="")
    reverted_reason: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AbEvaluationRun(Base):
    """Aggregated A/B metrics only — no face crops/embeddings/names."""

    __tablename__ = "ab_evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("camera_devices.id"), nullable=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_mix: Mapped[str] = mapped_column(String(64), default="")  # MOCK|REPLAY|LIVE mix label
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    blockers_json: Mapped[str] = mapped_column(Text, default="[]")
    can_auto_enable: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|REJECTED|APPROVED
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note_vi: Mapped[str] = mapped_column(Text, default="")
    # PR7: trust class — client imports stay UNTRUSTED_IMPORT forever
    evidence_class: Mapped[str] = mapped_column(String(32), default="UNTRUSTED_IMPORT")
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")


class CameraLabRun(Base):
    """Server-issued physical lab run — CREATED→LIVE_MEASURED→OWNER_REVIEWED→PHYSICAL_VERIFIED."""

    __tablename__ = "camera_lab_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # CAMERA_LAB|FACE_PILOT
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), nullable=False, index=True)
    # CREATED|LIVE_MEASURED|OWNER_REVIEWED|PHYSICAL_VERIFIED|REJECTED|REVOKED
    state: Mapped[str] = mapped_column(String(32), default="CREATED")
    profile: Mapped[str] = mapped_column(String(32), default="MAIN")
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    provenance: Mapped[str] = mapped_column(String(32), default="")
    source_generation: Mapped[str] = mapped_column(String(64), default="")
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")
    decoded_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decoded_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps_measured: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_age_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0)
    decode_errors: Mapped[int] = mapped_column(Integer, default=0)
    owner_challenge: Mapped[str] = mapped_column(String(64), default="")
    owner_reviewed_by: Mapped[str] = mapped_column(String(128), default="")
    owner_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    note_vi: Mapped[str] = mapped_column(Text, default="")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")


class FacePilotCaseEvent(Base):
    """Server-generated per-case FACE_PILOT evaluation — no images/embeddings stored."""

    __tablename__ = "face_pilot_case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    lab_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_id: Mapped[str] = mapped_column(String(64), default="")
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    # KNOWN:<employee_id> | UNKNOWN
    truth_label: Mapped[str] = mapped_column(String(64), nullable=False)
    pred_label: Mapped[str] = mapped_column(String(64), default="")
    outcome: Mapped[str] = mapped_column(String(32), default="")  # CORRECT|WRONG|MISS|FALSE_ACCEPT|AMBIGUOUS|NO_FACE
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str] = mapped_column(String(32), default="DAY")  # DAY|DUSK|NIGHT_IR|BACKLIGHT
    native_face_width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note_vi: Mapped[str] = mapped_column(Text, default="")


class PilotEvidenceRecord(Base):
    """Append-only lab / face-pilot evidence — PHYSICAL_VERIFIED required before signing gates."""

    __tablename__ = "pilot_evidence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # CAMERA_LAB|FACE_PILOT|AB_REVIEW
    evidence_class: Mapped[str] = mapped_column(String(32), nullable=False)
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), nullable=False, index=True)
    lab_run_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    provenance: Mapped[str] = mapped_column(String(32), default="")
    decoded_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decoded_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps_measured: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")
    windows_host: Mapped[str] = mapped_column(String(128), default="")
    labeled_known: Mapped[int] = mapped_column(Integer, default=0)
    labeled_unknown: Mapped[int] = mapped_column(Integer, default=0)
    frame_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    ab_run_id: Mapped[str] = mapped_column(String(64), default="")
    operator: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    note_vi: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotApprovalRecord(Base):
    """HMAC-signed owner pilot / AUTO_VALIDATED approvals — server issued only."""

    __tablename__ = "pilot_approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # CAMERA_LAB|FACE_PILOT|AUTO_VALIDATED
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("camera_devices.id"), nullable=True)
    model_hash_pin: Mapped[str] = mapped_column(String(128), default="")
    gallery_revision_pin: Mapped[str] = mapped_column(String(128), default="")
    threshold_id_pin: Mapped[str] = mapped_column(String(128), default="")
    ab_run_id: Mapped[str] = mapped_column(String(64), default="")
    evidence_id: Mapped[str] = mapped_column(String(64), default="")
    issued_by: Mapped[str] = mapped_column(String(128), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signature: Mapped[str] = mapped_column(String(128), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    note_vi: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class CameraLiveBinding(Base):
    """Persisted LIVE bind metadata (no credentials) — restore after restart."""

    __tablename__ = "camera_live_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("camera_devices.id"), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), default="rtsp")
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int] = mapped_column(Integer, default=554)
    path: Mapped[str] = mapped_column(String(255), default="")
    profile: Mapped[str] = mapped_column(String(32), default="MAIN")
    resolved_ips_json: Mapped[str] = mapped_column(Text, default="[]")
    config_revision: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecretFsOutbox(Base):
    """Commit-proven credential filesystem intents — only committed rows are replayed."""

    __tablename__ = "secret_fs_outbox"
    __table_args__ = (UniqueConstraint("public_id", name="uq_secret_fs_outbox_public_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    staged_ref: Mapped[str] = mapped_column(String(255), default="")
    live_ref: Mapped[str] = mapped_column(String(255), default="")
    delete_ref: Mapped[str] = mapped_column(String(255), default="")
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

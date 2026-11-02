"""Application and operational attendance settings (v1.5 defaults)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AfternoonSelectionPolicy(BaseModel):
    """Deterministic PM reference selection around 18:00 (v1.5)."""

    reference_time: str = "18:00:00"
    near_tolerance_before_minutes: int = 5
    near_tolerance_after_minutes: int = 5
    prefer_earlier_on_tie: bool = True
    earlier_fallback_enabled: bool = True
    preferred_photo_start: str = "17:55:00"
    preferred_photo_end: str = "18:00:00"
    selection_policy_version: str = "v1.5-nearest-earlier-fallback"


class AttendanceWindows(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    workdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])  # Mon-Sat
    shift_start: str = "08:30:00"
    shift_end: str = "18:00:00"
    lunch_start: str = "12:00:00"
    lunch_end: str = "13:30:00"
    late_tolerance_seconds: int = 0
    morning_recognition_start: str = "08:15:00"
    morning_recognition_end: str = "08:45:00"  # inclusive through 08:45:00.999… via end exclusive +1s in engine
    # v1.5 CORRECTION: afternoon window through END of minute 23:55 → [17:00, 23:56)
    afternoon_recognition_start: str = "17:00:00"
    afternoon_recognition_end_exclusive: str = "23:56:00"
    overtime_boundary: str = "18:00:00"
    overtime_monitor_end_exclusive: str = "23:56:00"
    afternoon_selection: AfternoonSelectionPolicy = Field(
        default_factory=AfternoonSelectionPolicy
    )


class OperationalConfig(BaseModel):
    """Versioned hot-apply payload."""

    version: int = 1
    shift_id: str = "MYPC-ADMIN-01"
    windows: AttendanceWindows = Field(default_factory=AttendanceWindows)
    mock_camera_enabled: bool = True
    exit_verification_gate: str = "BLOCKED"  # until real camera calibration
    listen_host: str = "127.0.0.1"
    listen_port: int = 8765
    lan_access_enabled: bool = False

    def impact_summary_vi(self) -> str:
        w = self.windows
        return (
            f"Ca {self.shift_id}: {w.shift_start}–{w.shift_end}; "
            f"nhận diện sáng {w.morning_recognition_start}–{w.morning_recognition_end}; "
            f"nhận diện chiều [{w.afternoon_recognition_start}, {w.afternoon_recognition_end_exclusive}); "
            f"mốc tham chiếu {w.afternoon_selection.reference_time}; "
            f"cổng xác minh ra về={self.exit_verification_gate}."
        )


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYPC_", env_file=".env", extra="ignore")

    app_name: str = "MyPC Attendance"
    app_version: str = "0.2.0-p01"
    spec_version: str = "1.5"
    # production | development | demo — mock observation only in development/demo
    app_env: str = "production"
    demo_mode: bool = False
    allow_mock_observation: bool = False
    data_dir: Path = Path("./data")
    database_url: str = ""
    # Empty by default — create_app loads/creates persistent CSPRNG secret under data_dir.
    # Historic weak default MUST NOT be used as production signer.
    secret_key: str = ""
    session_max_age_seconds: int = 60 * 60 * 8
    # Owner-signed gates (server records); never invent PASS from TCP alone
    camera_lab_pass: bool = False
    face_pilot_pass: bool = False
    allow_live_enrollment_staging: bool = False  # requires signed pilot approval object
    bootstrap_password: str = ""  # only for first-run / tests via env
    bootstrap_username: str = "admin"
    require_password_change: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:8765"])
    models_dir: Path = Path("./models/weights")
    # Synthetic fixture keys / force_slot only when explicitly enabled (CI/dev).
    # Production must keep this False even for ENROLLMENT_MANAGE operators.
    allow_synthetic_fixtures: bool = False
    allow_force_slot: bool = False
    # Live RTSP/ONVIF gateway (still distinct from CAMERA_LAB_PASS)
    camera_gateway_enabled: bool = True
    go2rtc_enabled: bool = False  # optional localhost restreamer; never bind to LAN by default

    @field_validator("data_dir", "models_dir", mode="before")
    @classmethod
    def _path(cls, v: Any) -> Path:
        return Path(v)

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_dir / "mypc_attendance.sqlite3"
        return f"sqlite:///{db_path.resolve()}"

    def is_production(self) -> bool:
        return self.app_env == "production" and not self.demo_mode

    def mock_ingest_allowed(self) -> bool:
        """Production never allows mock observation ingest into attendance."""
        if self.is_production():
            return False
        return bool(self.allow_mock_observation or self.demo_mode or self.app_env == "development")

    def synthetic_fixtures_allowed(self) -> bool:
        if self.is_production():
            return False
        return bool(self.allow_synthetic_fixtures or self.demo_mode or self.app_env in {"development", "demo", "test"})

    def force_slot_allowed(self) -> bool:
        if self.is_production():
            return False
        return bool(self.allow_force_slot or self.synthetic_fixtures_allowed())



def default_operational_config() -> OperationalConfig:
    return OperationalConfig()

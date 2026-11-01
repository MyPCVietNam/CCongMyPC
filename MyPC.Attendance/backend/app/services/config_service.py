"""Versioned operational config with apply ACK protocol."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.settings import OperationalConfig, default_operational_config
from app.models.entities import AuditLog, ConfigRevision


class ConfigService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._active: OperationalConfig = default_operational_config()
        self._ack_at: datetime | None = None

    @property
    def active(self) -> OperationalConfig:
        return self._active

    @property
    def ack_at(self) -> datetime | None:
        return self._ack_at

    def load_from_db(self, session: Session) -> OperationalConfig:
        row = session.scalar(
            select(ConfigRevision)
            .where(ConfigRevision.status == "APPLIED")
            .order_by(ConfigRevision.version.desc())
        )
        if row is None:
            cfg = default_operational_config()
            self._persist_applied(session, cfg, actor="system", reason="bootstrap-default")
            return self._active
        self._active = OperationalConfig.model_validate_json(row.payload_json)
        self._ack_at = row.active_ack_at
        return self._active

    def save_draft(
        self,
        session: Session,
        payload: OperationalConfig,
        *,
        actor: str,
        expected_version: int | None,
        reason: str,
    ) -> ConfigRevision:
        if expected_version is not None and expected_version != self._active.version:
            raise ConfigConflictError(
                f"Phiên bản cấu hình đã thay đổi (hiện tại {self._active.version}, gửi {expected_version})"
            )
        draft = payload.model_copy(deep=True)
        draft.version = self._active.version  # draft keeps current until apply
        checksum = hashlib.sha256(draft.model_dump_json().encode()).hexdigest()
        rev = ConfigRevision(
            version=self._next_version(session),
            effective_at=self._clock.now_utc(),
            applied_by=actor,
            payload_json=draft.model_dump_json(),
            checksum=checksum,
            active_ack_at=None,
            reason=reason,
            status="DRAFT",
        )
        session.add(rev)
        session.flush()
        return rev

    def apply(
        self,
        session: Session,
        *,
        actor: str,
        expected_version: int,
        payload: OperationalConfig,
        reason: str,
        simulate_ack_failure: bool = False,
    ) -> tuple[OperationalConfig, bool, str]:
        if expected_version != self._active.version:
            raise ConfigConflictError(
                f"Xung đột phiên bản cấu hình (hiện tại {self._active.version})"
            )
        new_cfg = payload.model_copy(deep=True)
        new_cfg.version = self._active.version + 1
        # Validate afternoon window never silently uses 19:00
        end = new_cfg.windows.afternoon_recognition_end_exclusive
        if end == "19:00:00":
            raise ValueError(
                "Cửa sổ chiều 19:00 không còn hợp lệ theo v1.5 — dùng 23:56:00 (hết phút 23:55)"
            )

        checksum = hashlib.sha256(new_cfg.model_dump_json().encode()).hexdigest()
        now = self._clock.now_utc()
        if simulate_ack_failure:
            rev = ConfigRevision(
                version=new_cfg.version,
                effective_at=now,
                applied_by=actor,
                payload_json=new_cfg.model_dump_json(),
                checksum=checksum,
                active_ack_at=None,
                reason=reason,
                status="FAILED",
            )
            session.add(rev)
            session.add(
                AuditLog(
                    actor=actor,
                    action="settings.apply_failed",
                    entity_type="config",
                    entity_id=str(new_cfg.version),
                    reason=reason,
                    timestamp=now,
                )
            )
            return self._active, False, "Cấu hình chưa thể áp dụng vì dịch vụ camera chưa phản hồi"

        self._active = new_cfg
        self._ack_at = now
        rev = ConfigRevision(
            version=new_cfg.version,
            effective_at=now,
            applied_by=actor,
            payload_json=new_cfg.model_dump_json(),
            checksum=checksum,
            active_ack_at=now,
            reason=reason,
            status="APPLIED",
        )
        session.add(rev)
        session.add(
            AuditLog(
                actor=actor,
                action="settings.apply",
                entity_type="config",
                entity_id=str(new_cfg.version),
                after_checksum=checksum,
                reason=reason,
                timestamp=now,
            )
        )
        return self._active, True, "Thay đổi đã được áp dụng thành công"

    def _persist_applied(
        self, session: Session, cfg: OperationalConfig, *, actor: str, reason: str
    ) -> None:
        now = self._clock.now_utc()
        checksum = hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()
        session.add(
            ConfigRevision(
                version=cfg.version,
                effective_at=now,
                applied_by=actor,
                payload_json=cfg.model_dump_json(),
                checksum=checksum,
                active_ack_at=now,
                reason=reason,
                status="APPLIED",
            )
        )
        self._active = cfg
        self._ack_at = now

    def _next_version(self, session: Session) -> int:
        row = session.scalar(select(ConfigRevision).order_by(ConfigRevision.version.desc()))
        return 1 if row is None else row.version + 1


class ConfigConflictError(Exception):
    pass

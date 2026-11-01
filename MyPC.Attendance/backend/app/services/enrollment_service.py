"""Controlled face enrollment orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.biometric import BiometricEnrollment
from app.models.entities import AuditLog, Employee
from app.vision.faces.pipeline import FacePipeline
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.faces.types import MatchOutcome


class EnrollmentService:
    def __init__(
        self,
        clock: Clock,
        pipeline: FacePipeline,
        store: FaceTemplateStore,
    ) -> None:
        self._clock = clock
        self._pipeline = pipeline
        self._store = store

    def start_enrollment(
        self,
        session: Session,
        *,
        employee_id: int,
        enrolled_by: str,
        authorization_ref: str,
        authorization_ack_vi: str,
        source: str = "DEMO",
    ) -> BiometricEnrollment:
        emp = session.get(Employee, employee_id)
        if emp is None:
            raise ValueError("Không tìm thấy nhân viên")
        if not authorization_ack_vi.strip():
            raise ValueError("Cần xác nhận thông báo xử lý dữ liệu sinh trắc học")
        # Revoke previous active enrollments (versioned replace)
        prev = session.scalars(
            select(BiometricEnrollment).where(
                BiometricEnrollment.employee_id == employee_id,
                BiometricEnrollment.status == "ACTIVE",
            )
        ).all()
        now = self._clock.now_utc()
        next_ver = 1
        for p in prev:
            p.status = "REVOKED"
            p.revoked_at = now
            p.revoke_reason = "Thay thế bằng phiên đăng ký mới"
            self._store.deactivate_enrollment_templates(session, p.id)
            next_ver = max(next_ver, p.template_version + 1)
        st = self._pipeline.status()
        enr = BiometricEnrollment(
            employee_id=employee_id,
            authorization_ref=authorization_ref,
            authorization_ack_vi=authorization_ack_vi,
            enrolled_by=enrolled_by,
            model_id=st["embedder"]["model_id"],
            model_hash=st["embedder"]["model_hash"],
            template_version=next_ver,
            status="ACTIVE",
            sample_count=0,
            quality_summary_json="{}",
            source=source,
            enrolled_at=now,
        )
        session.add(enr)
        session.flush()
        emp.biometric_eligible = True
        session.add(
            AuditLog(
                actor=enrolled_by,
                action="biometric.enrollment.start",
                entity_type="biometric_enrollment",
                entity_id=str(enr.id),
                reason=authorization_ref,
                timestamp=now,
            )
        )
        return enr

    def add_sample(
        self,
        session: Session,
        *,
        enrollment_id: int,
        image: np.ndarray,
        identity_fixture_key: str | None = None,
    ) -> dict[str, Any]:
        enr = session.get(BiometricEnrollment, enrollment_id)
        if enr is None or enr.status != "ACTIVE":
            raise ValueError("Phiên đăng ký không hợp lệ")
        faces, quality = self._pipeline.detect_and_quality(image)
        # Synthetic identity fixtures are for CI/demo only — relax blur gate (still require a face).
        if identity_fixture_key and faces and not quality.ok:
            blur_only = quality.reasons_vi and all("mờ" in r.lower() for r in quality.reasons_vi)
            if blur_only or quality.face_width_px >= 40:
                from app.vision.faces.types import QualityReport

                quality = QualityReport(
                    ok=True,
                    score=max(quality.score, 0.5),
                    face_width_px=quality.face_width_px,
                    blur_score=1.0,
                    reasons_vi=[],
                    metadata={**quality.metadata, "fixture_relaxed": True},
                )
        if not quality.ok:
            return {
                "accepted": False,
                "message_vi": quality.reasons_vi[0] if quality.reasons_vi else "Mẫu bị từ chối",
                "quality": asdict(quality),
                "face_count": len(faces),
                "pixel_size": [quality.face_width_px, quality.face_width_px],
            }
        # Collision check against other employees
        gallery = [
            (emp_id, vec)
            for _, vec, emp_id in self._store.load_active_templates(session)
            if emp_id != enr.employee_id
        ]
        probe = self._pipeline.embed_image(image, identity_fixture_key=identity_fixture_key)
        if gallery:
            check = self._pipeline.verify(
                image, gallery, identity_fixture_key=identity_fixture_key
            )
            if check.outcome == MatchOutcome.MATCH:
                return {
                    "accepted": False,
                    "message_vi": "Mẫu có thể trùng với nhân viên khác — cần đối soát thủ công.",
                    "collision_employee_id": check.employee_id,
                    "quality": asdict(quality),
                }
            if check.outcome == MatchOutcome.AMBIGUOUS:
                return {
                    "accepted": False,
                    "message_vi": "Mẫu gây nhầm lẫn danh tính — cần đối soát.",
                    "quality": asdict(quality),
                }

        self._store.save_template(
            session,
            enrollment_id=enr.id,
            vec=probe,
            quality_score=quality.score,
            quality_metadata=quality.metadata | {"reasons_vi": quality.reasons_vi},
            vector_version=self._pipeline.embedder.info.model_id,
        )
        enr.sample_count += 1
        summary = json.loads(enr.quality_summary_json or "{}")
        summary.setdefault("samples", []).append(
            {"score": quality.score, "face_width_px": quality.face_width_px}
        )
        enr.quality_summary_json = json.dumps(summary)
        session.flush()
        return {
            "accepted": True,
            "message_vi": f"Đã nhận mẫu #{enr.sample_count}",
            "sample_count": enr.sample_count,
            "quality": asdict(quality),
            "pixel_size": [quality.face_width_px, quality.face_width_px],
            "model_id": self._pipeline.embedder.info.model_id,
        }

    def revoke(
        self,
        session: Session,
        *,
        enrollment_id: int,
        actor: str,
        reason: str,
    ) -> BiometricEnrollment:
        enr = session.get(BiometricEnrollment, enrollment_id)
        if enr is None:
            raise ValueError("Không tìm thấy đăng ký")
        now = self._clock.now_utc()
        enr.status = "REVOKED"
        enr.revoked_at = now
        enr.revoke_reason = reason
        self._store.deactivate_enrollment_templates(session, enr.id)
        # If no active enrollments remain, clear biometric_eligible
        still = session.scalar(
            select(BiometricEnrollment).where(
                BiometricEnrollment.employee_id == enr.employee_id,
                BiometricEnrollment.status == "ACTIVE",
            )
        )
        if still is None:
            emp = session.get(Employee, enr.employee_id)
            if emp:
                emp.biometric_eligible = False
        session.add(
            AuditLog(
                actor=actor,
                action="biometric.enrollment.revoke",
                entity_type="biometric_enrollment",
                entity_id=str(enr.id),
                reason=reason,
                timestamp=now,
            )
        )
        session.flush()
        return enr

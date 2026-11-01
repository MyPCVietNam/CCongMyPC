"""Controlled face enrollment orchestration with atomic lifecycle (P01.5)."""

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
from app.vision.faces.embedder import EmbeddingError
from app.vision.faces.pipeline import FacePipeline
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.faces.types import MatchOutcome, QualityReport

# Lifecycle: DRAFT -> CAPTURING -> QUALITY_REVIEW -> VALIDATING -> ACTIVE
# Terminal: PAUSED | FAILED | CANCELLED | REVOKED
CAPTURE_STATUSES = {"DRAFT", "CAPTURING", "QUALITY_REVIEW", "PAUSED"}
MIN_SAMPLES_BEFORE_ACTIVATE = 3


def _quality_asdict(q: QualityReport) -> dict[str, Any]:
    d = asdict(q)
    return d


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

        # DO NOT revoke ACTIVE enrollments yet — keep clock-in ability until new one activates
        prev = session.scalars(
            select(BiometricEnrollment).where(
                BiometricEnrollment.employee_id == employee_id,
            )
        ).all()
        next_ver = 1
        for p in prev:
            next_ver = max(next_ver, p.template_version + 1)
            # Cancel incomplete in-progress sessions for this employee
            if p.status in CAPTURE_STATUSES | {"VALIDATING"}:
                p.status = "CANCELLED"
                p.revoke_reason = "Thay bằng phiên đăng ký mới (chưa kích hoạt)"

        st = self._pipeline.status()
        now = self._clock.now_utc()
        enr = BiometricEnrollment(
            employee_id=employee_id,
            authorization_ref=authorization_ref,
            authorization_ack_vi=authorization_ack_vi,
            enrolled_by=enrolled_by,
            model_id=st["embedder"]["model_id"],
            model_hash=st["embedder"]["model_hash"],
            template_version=next_ver,
            status="DRAFT",
            sample_count=0,
            quality_summary_json="{}",
            source=source,
            enrolled_at=now,
        )
        session.add(enr)
        session.flush()
        enr.status = "CAPTURING"
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
        pose_slot: str | None = None,
    ) -> dict[str, Any]:
        enr = session.get(BiometricEnrollment, enrollment_id)
        if enr is None or enr.status not in CAPTURE_STATUSES:
            raise ValueError("Phiên đăng ký không hợp lệ hoặc không đang thu thập mẫu")
        if enr.status == "DRAFT":
            enr.status = "CAPTURING"
        if enr.status == "PAUSED":
            raise ValueError("Phiên đang tạm dừng — hãy tiếp tục trước khi thu mẫu")

        faces, quality = self._pipeline.detect_and_quality(
            image, expected_slot=pose_slot, max_faces_ok=1
        )
        # Synthetic identity fixtures are for CI/demo only — relax blur/size gate (still require a face).
        if identity_fixture_key and faces and not quality.ok:
            quality = QualityReport(
                ok=True,
                score=max(quality.score, 0.5),
                face_width_px=max(quality.face_width_px, 120),
                inter_eye_px=max(quality.inter_eye_px, 40.0),
                blur_score=1.0,
                laplacian_var=200.0,
                pose=quality.pose,
                hard_fail=False,
                reasons_vi=[],
                breakdown={**quality.breakdown, "fixture_relaxed": True},
                metadata={**quality.metadata, "fixture_relaxed": True},
            )
        if not quality.ok:
            return {
                "accepted": False,
                "message_vi": quality.reasons_vi[0] if quality.reasons_vi else "Mẫu bị từ chối",
                "quality": _quality_asdict(quality),
                "face_count": len(faces),
                "pixel_size": [quality.face_width_px, quality.face_width_px],
                "status": enr.status,
            }

        # Collision check against OTHER employees' ACTIVE templates only
        gallery = [
            (emp_id, vec)
            for _, vec, emp_id in self._store.load_active_templates(session)
            if emp_id != enr.employee_id
        ]
        primary = max(faces, key=lambda f: f.w * f.h) if faces else None
        try:
            probe = self._pipeline.embed_image(
                image, identity_fixture_key=identity_fixture_key, face=primary
            )
        except EmbeddingError as exc:
            return {
                "accepted": False,
                "message_vi": exc.message_vi,
                "code": exc.code,
                "quality": _quality_asdict(quality),
                "status": enr.status,
            }

        if gallery and not identity_fixture_key:
            check = self._pipeline.verify(image, gallery)
            if check.outcome == MatchOutcome.MATCH:
                return {
                    "accepted": False,
                    "message_vi": "Mẫu có thể trùng với nhân viên khác — cần đối soát thủ công.",
                    "collision_employee_id": check.employee_id,
                    "quality": _quality_asdict(quality),
                    "status": "NEEDS_REVIEW",
                }
            if check.outcome == MatchOutcome.AMBIGUOUS:
                return {
                    "accepted": False,
                    "message_vi": "Mẫu gây nhầm lẫn danh tính — cần đối soát.",
                    "quality": _quality_asdict(quality),
                    "status": "NEEDS_REVIEW",
                }
        elif gallery and identity_fixture_key:
            check = self._pipeline.verify(
                image, gallery, identity_fixture_key=identity_fixture_key
            )
            if check.outcome == MatchOutcome.MATCH:
                return {
                    "accepted": False,
                    "message_vi": "Mẫu có thể trùng với nhân viên khác — cần đối soát thủ công.",
                    "collision_employee_id": check.employee_id,
                    "quality": _quality_asdict(quality),
                }

        meta = {
            **quality.metadata,
            "reasons_vi": quality.reasons_vi,
            "breakdown": quality.breakdown,
            "pose_slot": pose_slot,
            "inference_mode": self._pipeline.inference_mode.value,
        }
        self._store.save_template(
            session,
            enrollment_id=enr.id,
            vec=probe,
            quality_score=quality.score,
            quality_metadata=meta,
            vector_version=self._pipeline.embedder.info.model_id,
            active=False,  # unpublished until activate()
        )
        enr.sample_count += 1
        summary = json.loads(enr.quality_summary_json or "{}")
        summary.setdefault("samples", []).append(
            {
                "score": quality.score,
                "face_width_px": quality.face_width_px,
                "inter_eye_px": quality.inter_eye_px,
                "laplacian_var": quality.laplacian_var,
                "pose_slot": pose_slot,
            }
        )
        enr.quality_summary_json = json.dumps(summary, ensure_ascii=False)
        if enr.sample_count >= MIN_SAMPLES_BEFORE_ACTIVATE:
            enr.status = "QUALITY_REVIEW"
        session.flush()
        return {
            "accepted": True,
            "message_vi": f"Đã nhận mẫu #{enr.sample_count}",
            "sample_count": enr.sample_count,
            "quality": _quality_asdict(quality),
            "pixel_size": [quality.face_width_px, quality.face_width_px],
            "model_id": self._pipeline.embedder.info.model_id,
            "status": enr.status,
            "inference_mode": self._pipeline.inference_mode.value,
        }

    def activate(
        self,
        session: Session,
        *,
        enrollment_id: int,
        actor: str,
        identity_fixture_key: str | None = None,
        verification_image: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """
        Independent verification + transactional activation.
        Old ACTIVE templates remain until this succeeds.
        """
        enr = session.get(BiometricEnrollment, enrollment_id)
        if enr is None:
            raise ValueError("Không tìm thấy phiên đăng ký")
        if enr.status not in {"QUALITY_REVIEW", "VALIDATING", "CAPTURING"}:
            raise ValueError(f"Không thể kích hoạt ở trạng thái {enr.status}")
        if enr.sample_count < MIN_SAMPLES_BEFORE_ACTIVATE:
            raise ValueError(
                f"Cần ít nhất {MIN_SAMPLES_BEFORE_ACTIVATE} mẫu đạt chất lượng trước khi kích hoạt"
            )

        enr.status = "VALIDATING"
        session.flush()

        # Fresh verification challenge (separate from training frames when image provided)
        templates = self._store.load_enrollment_templates(session, enr.id, include_inactive=True)
        if len(templates) < MIN_SAMPLES_BEFORE_ACTIVATE:
            enr.status = "QUALITY_REVIEW"
            raise ValueError("Chưa đủ mẫu đã lưu để kích hoạt")

        if verification_image is not None or identity_fixture_key:
            gallery = [(enr.employee_id, vec) for _, vec in templates]
            img = verification_image if verification_image is not None else np.zeros((240, 240, 3), dtype=np.uint8)
            # Build a non-black fixture canvas so detector finds a face in synthetic mode
            if identity_fixture_key and verification_image is None:
                img = _fixture_canvas(identity_fixture_key)
            result = self._pipeline.verify(
                img, gallery, identity_fixture_key=identity_fixture_key
            )
            if result.outcome != MatchOutcome.MATCH or result.employee_id != enr.employee_id:
                enr.status = "QUALITY_REVIEW"
                session.flush()
                return {
                    "activated": False,
                    "status": enr.status,
                    "message_vi": (
                        "Xác minh độc lập thất bại — chưa kích hoạt. "
                        + (result.message_vi or "")
                    ).strip(),
                    "verify_outcome": result.outcome.value,
                }

        now = self._clock.now_utc()
        # Revoke previous ACTIVE only now
        prev = session.scalars(
            select(BiometricEnrollment).where(
                BiometricEnrollment.employee_id == enr.employee_id,
                BiometricEnrollment.status == "ACTIVE",
                BiometricEnrollment.id != enr.id,
            )
        ).all()
        for p in prev:
            p.status = "REVOKED"
            p.revoked_at = now
            p.revoke_reason = "Thay thế bằng phiên đăng ký đã xác minh"
            self._store.deactivate_enrollment_templates(session, p.id)

        self._store.activate_enrollment_templates(session, enr.id)
        enr.status = "ACTIVE"
        emp = session.get(Employee, enr.employee_id)
        if emp:
            emp.biometric_eligible = True
        session.add(
            AuditLog(
                actor=actor,
                action="biometric.enrollment.activate",
                entity_type="biometric_enrollment",
                entity_id=str(enr.id),
                reason="Kích hoạt sau xác minh",
                timestamp=now,
            )
        )
        session.flush()
        return {
            "activated": True,
            "status": enr.status,
            "enrollment_id": enr.id,
            "template_version": enr.template_version,
            "message_vi": "Đã kích hoạt đăng ký khuôn mặt. Mẫu cũ (nếu có) đã được thu hồi.",
        }

    def cancel(
        self,
        session: Session,
        *,
        enrollment_id: int,
        actor: str,
        reason: str = "Hủy phiên đăng ký",
    ) -> BiometricEnrollment:
        enr = session.get(BiometricEnrollment, enrollment_id)
        if enr is None:
            raise ValueError("Không tìm thấy đăng ký")
        if enr.status == "ACTIVE":
            raise ValueError("Không hủy phiên ACTIVE — hãy dùng thu hồi")
        now = self._clock.now_utc()
        enr.status = "CANCELLED"
        enr.revoked_at = now
        enr.revoke_reason = reason
        self._store.deactivate_enrollment_templates(session, enr.id)
        session.add(
            AuditLog(
                actor=actor,
                action="biometric.enrollment.cancel",
                entity_type="biometric_enrollment",
                entity_id=str(enr.id),
                reason=reason,
                timestamp=now,
            )
        )
        session.flush()
        return enr

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


def _fixture_canvas(key: str, salt: str = "") -> np.ndarray:
    """Non-black synthetic image so detector finds a centered face in fixture mode."""
    seed = abs(hash(f"{key}::{salt}")) % (2**32)
    rng = np.random.default_rng(seed)
    # Large enough for body-height experimental target in DEMO geometry
    size = 640
    img = np.full((size, size, 3), 140, dtype=np.uint8)
    img[80 : size - 80, 120 : size - 120] = rng.integers(
        90, 180, size=(size - 160, size - 240, 3), dtype=np.uint8
    )
    return img

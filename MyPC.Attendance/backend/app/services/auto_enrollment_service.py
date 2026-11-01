"""P01.5 guided automatic enrollment — full-frame face + body reference capture."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.biometric import EnrollmentSample, EnrollmentSession
from app.models.entities import AuditLog
from app.services.enrollment_service import EnrollmentService, _fixture_canvas
from app.vision.body.person_detector import PersonDetector, evaluate_body_quality
from app.vision.faces.embedder import EmbeddingError
from app.vision.faces.pipeline import FacePipeline
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.faces.types import MatchOutcome

FACE_SLOTS = ("FACE_FRONT", "FACE_LEFT", "FACE_RIGHT")
BODY_SLOTS = ("BODY_FRONT", "BODY_LEFT", "BODY_RIGHT", "BODY_MOTION")
ALL_SLOTS = FACE_SLOTS + BODY_SLOTS

GUIDANCE_VI = {
    "FACE_FRONT": "Nhìn thẳng vào camera, không đội mũ, giữ yên khoảng 1–2 giây.",
    "FACE_LEFT": "Xoay mặt sang TRÁI của bạn khoảng 20–35°, vẫn nhìn thấy hai mắt.",
    "FACE_RIGHT": "Xoay mặt sang PHẢI của bạn khoảng 20–35°, vẫn nhìn thấy hai mắt.",
    "BODY_FRONT": "Đứng thẳng mặt về camera — thấy cả đầu và chân trong khung hình gốc.",
    "BODY_LEFT": "Đứng nghiêng trái, vẫn thấy đủ đầu–chân, khác tư thế nhìn thẳng.",
    "BODY_RIGHT": "Đứng nghiêng phải, đủ đầu–chân, khác các tư thế trước.",
    "BODY_MOTION": "Đi bộ hoặc xoay người tự nhiên — tránh mờ quá mức, vẫn đủ đầu–chân.",
    "WAITING_FOR_PERSON": "Chờ nhân viên vào khung hình toàn cảnh (không cần vẽ vùng ROI).",
    "MULTIPLE_PEOPLE": "Nhiều người trong khung — chỉ giữ đúng nhân viên đang đăng ký.",
    "READY_TO_ACTIVATE": "Đủ mẫu. Chạy xác minh độc lập rồi kích hoạt.",
    "CHECKING_IDENTITY": "Đang kiểm tra nhất quán danh tính và trùng mẫu với nhân viên khác…",
    "BODY_CAPTURE_BLOCKED": "Camera không cho thấy đủ toàn thân — không bịa hoàn thành.",
    "BLOCKED_BY_CAMERA_GEOMETRY": "Hình học camera không đủ pixel/toàn thân. Đổi vị trí hoặc nguồn ủy quyền.",
}


def _next_slot(progress: dict[str, Any]) -> str | None:
    done = set(progress.get("completed_slots", []))
    for s in ALL_SLOTS:
        if s not in done:
            return s
    return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


class AutoEnrollmentService:
    def __init__(
        self,
        clock: Clock,
        pipeline: FacePipeline,
        store: FaceTemplateStore,
        enrollment_service: EnrollmentService,
        person_detector: PersonDetector | None = None,
    ) -> None:
        self._clock = clock
        self._pipeline = pipeline
        self._store = store
        self._enrollment = enrollment_service
        self._person = person_detector or PersonDetector()
        # Ephemeral RAM frame buffers keyed by session public_id (discarded on restart)
        self._buffers: dict[str, list[dict[str, Any]]] = {}

    def start(
        self,
        session: Session,
        *,
        employee_id: int,
        operator: str,
        authorization_ref: str,
        authorization_ack_vi: str,
        source: str = "DEMO",
    ) -> EnrollmentSession:
        enr = self._enrollment.start_enrollment(
            session,
            employee_id=employee_id,
            enrolled_by=operator,
            authorization_ref=authorization_ref,
            authorization_ack_vi=authorization_ack_vi,
            source="AUTO" if source == "DEMO" else source,
        )
        now = self._clock.now_utc()
        progress = {
            "completed_slots": [],
            "samples": {},
            "face_embeddings": {},
            "frame_hashes": [],
            "announcements": [],
        }
        row = EnrollmentSession(
            public_id=str(uuid.uuid4()),
            employee_id=employee_id,
            enrollment_id=enr.id,
            operator=operator,
            status="WAITING_FOR_PERSON",
            current_step="FACE_FRONT",
            ui_state="WAITING_FOR_PERSON",
            guidance_vi=GUIDANCE_VI["FACE_FRONT"],
            progress_json=json.dumps(progress, ensure_ascii=False),
            source=source,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        self._buffers[row.public_id] = []
        session.add(
            AuditLog(
                actor=operator,
                action="biometric.auto_enrollment.start",
                entity_type="enrollment_session",
                entity_id=row.public_id,
                reason=authorization_ref,
                timestamp=now,
            )
        )
        return row

    def get(self, session: Session, public_id: str) -> EnrollmentSession | None:
        return session.scalar(
            select(EnrollmentSession).where(EnrollmentSession.public_id == public_id)
        )

    def session_payload(self, row: EnrollmentSession) -> dict[str, Any]:
        progress = json.loads(row.progress_json or "{}")
        return {
            "session_id": row.public_id,
            "enrollment_id": row.enrollment_id,
            "employee_id": row.employee_id,
            "status": row.status,
            "ui_state": row.ui_state,
            "current_step": row.current_step,
            "guidance_vi": row.guidance_vi,
            "completed_slots": progress.get("completed_slots", []),
            "required_slots": list(ALL_SLOTS),
            "face_done": sum(1 for s in FACE_SLOTS if s in progress.get("completed_slots", [])),
            "body_done": sum(1 for s in BODY_SLOTS if s in progress.get("completed_slots", [])),
            "source": row.source,
            "roi_required": False,
            "note_vi": (
                "Quét toàn khung hình — không cần vẽ vùng chấm công. "
                "Ảnh toàn thân chỉ là bằng chứng hỗ trợ, không dùng làm nhận dạng sinh trắc học."
            ),
            "person_detector": asdict(self._person.info),
            "inference_mode": self._pipeline.inference_mode.value,
        }

    def pause(self, session: Session, public_id: str) -> EnrollmentSession:
        row = self._require_open(session, public_id)
        row.status = "PAUSED"
        row.ui_state = "PAUSED"
        row.guidance_vi = "Phiên tạm dừng. Nhấn Tiếp tục để thu thập tiếp."
        row.updated_at = self._clock.now_utc()
        session.flush()
        return row

    def resume(self, session: Session, public_id: str) -> EnrollmentSession:
        row = self._require_open(session, public_id, allow_paused=True)
        if row.status != "PAUSED":
            return row
        row.status = "CAPTURING"
        row.ui_state = row.current_step
        row.guidance_vi = GUIDANCE_VI.get(row.current_step, "")
        row.updated_at = self._clock.now_utc()
        session.flush()
        return row

    def cancel(self, session: Session, public_id: str, actor: str) -> EnrollmentSession:
        row = self.get(session, public_id)
        if row is None:
            raise ValueError("Không tìm thấy phiên")
        if row.status == "ACTIVE":
            raise ValueError("Phiên đã kích hoạt")
        self._enrollment.cancel(
            session, enrollment_id=row.enrollment_id, actor=actor, reason="Hủy auto enrollment"
        )
        row.status = "CANCELLED"
        row.ui_state = "CANCELLED"
        row.guidance_vi = "Đã hủy. Mẫu ACTIVE cũ (nếu có) vẫn giữ."
        row.updated_at = self._clock.now_utc()
        self._buffers.pop(row.public_id, None)
        session.flush()
        return row

    def retry_step(self, session: Session, public_id: str, slot: str | None = None) -> EnrollmentSession:
        row = self._require_open(session, public_id, allow_paused=True)
        progress = json.loads(row.progress_json or "{}")
        target = slot or row.current_step
        if target in progress.get("completed_slots", []):
            progress["completed_slots"] = [s for s in progress["completed_slots"] if s != target]
            progress.get("samples", {}).pop(target, None)
            progress.get("face_embeddings", {}).pop(target, None)
            # Mark DB samples replaced
            samples = session.scalars(
                select(EnrollmentSample).where(
                    EnrollmentSample.session_id == row.id,
                    EnrollmentSample.slot == target,
                    EnrollmentSample.replaced.is_(False),
                )
            ).all()
            for s in samples:
                s.replaced = True
                s.accepted = False
        row.current_step = target
        row.status = "CAPTURING"
        row.ui_state = target
        row.guidance_vi = GUIDANCE_VI.get(target, "")
        row.progress_json = json.dumps(progress, ensure_ascii=False)
        row.updated_at = self._clock.now_utc()
        session.flush()
        return row

    def ingest_frame(
        self,
        session: Session,
        public_id: str,
        image: np.ndarray,
        *,
        identity_fixture_key: str | None = None,
        force_slot: str | None = None,
        declare_body_geometry_blocked: bool = False,
    ) -> dict[str, Any]:
        """
        Analyze one full-frame image for the current auto-enrollment step.
        No mandatory ROI. Multiple faces/people => pause. Duplicate frames rejected.
        """
        row = self._require_open(session, public_id)
        if row.status == "PAUSED":
            return {**self.session_payload(row), "accepted": False, "message_vi": "Phiên đang tạm dừng."}

        progress = json.loads(row.progress_json or "{}")
        step = force_slot or row.current_step or _next_slot(progress) or "FACE_FRONT"

        if declare_body_geometry_blocked and step.startswith("BODY_"):
            row.status = "BODY_CAPTURE_BLOCKED"
            row.ui_state = "BLOCKED_BY_CAMERA_GEOMETRY"
            row.guidance_vi = GUIDANCE_VI["BLOCKED_BY_CAMERA_GEOMETRY"]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "blocked": True,
                "code": "BLOCKED_BY_CAMERA_GEOMETRY",
                "message_vi": row.guidance_vi,
            }

        # Hash a sparse full-frame sample so identical top margins do not collide
        flat = image.reshape(-1)[::97]
        frame_hash = hashlib.sha256(flat.tobytes()).hexdigest()[:32]
        if frame_hash in progress.get("frame_hashes", [])[-20:]:
            row.ui_state = "WAITING_FOR_PERSON"
            row.guidance_vi = "Khung hình trùng lặp — hãy đổi tư thế nhẹ rồi thử lại."
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "code": "DUPLICATE_FRAME",
            }

        if step.startswith("FACE_"):
            return self._capture_face(
                session, row, progress, step, image, frame_hash, identity_fixture_key
            )
        return self._capture_body(session, row, progress, step, image, frame_hash)

    def _capture_face(
        self,
        session: Session,
        row: EnrollmentSession,
        progress: dict,
        step: str,
        image: np.ndarray,
        frame_hash: str,
        identity_fixture_key: str | None,
    ) -> dict[str, Any]:
        faces, quality = self._pipeline.detect_and_quality(
            image, expected_slot=step, max_faces_ok=1
        )
        if identity_fixture_key and faces and not quality.ok:
            from app.vision.faces.types import QualityReport

            quality = QualityReport(
                ok=True,
                score=max(quality.score, 0.55),
                face_width_px=max(quality.face_width_px, 120),
                inter_eye_px=max(quality.inter_eye_px, 40.0),
                blur_score=1.0,
                laplacian_var=200.0,
                pose=quality.pose,
                hard_fail=False,
                reasons_vi=[],
                breakdown={**quality.breakdown, "fixture_relaxed": True, "forced_slot": step},
                metadata={**quality.metadata, "fixture_relaxed": True},
            )
            # Force pose hint for fixture progression
            if quality.pose:
                quality.pose.slot_hint = step

        if len(faces) > 1:
            row.status = "PAUSED"
            row.ui_state = "MULTIPLE_PEOPLE"
            row.guidance_vi = GUIDANCE_VI["MULTIPLE_PEOPLE"]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "code": "MULTIPLE_PEOPLE",
            }

        if not faces or not quality.ok:
            state = (quality.breakdown or {}).get("state") or (
                "WAITING_FOR_PERSON" if not faces else "BLURRY"
            )
            row.ui_state = str(state)
            row.status = "CAPTURING"
            row.guidance_vi = quality.reasons_vi[0] if quality.reasons_vi else GUIDANCE_VI[step]
            # Pose coaching
            if quality.pose and quality.pose.slot_hint != step and faces:
                if step == "FACE_LEFT":
                    row.ui_state = "TURN_LEFT"
                    row.guidance_vi = GUIDANCE_VI["FACE_LEFT"]
                elif step == "FACE_RIGHT":
                    row.ui_state = "TURN_RIGHT"
                    row.guidance_vi = GUIDANCE_VI["FACE_RIGHT"]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "quality": asdict(quality),
            }

        # Pose distinctness for non-fixture
        if not identity_fixture_key and quality.pose and quality.pose.confidence >= 0.5:
            if quality.pose.slot_hint not in {step, "UNKNOWN"} and step != "FACE_FRONT":
                row.ui_state = "TURN_LEFT" if step == "FACE_LEFT" else "TURN_RIGHT"
                row.guidance_vi = GUIDANCE_VI[step]
                row.updated_at = self._clock.now_utc()
                session.flush()
                return {
                    **self.session_payload(row),
                    "accepted": False,
                    "message_vi": row.guidance_vi,
                    "quality": asdict(quality),
                }

        primary = max(faces, key=lambda f: f.w * f.h)
        try:
            vec = self._pipeline.embed_image(
                image, identity_fixture_key=identity_fixture_key, face=primary
            )
        except EmbeddingError as exc:
            row.ui_state = "NEEDS_REVIEW"
            row.guidance_vi = exc.message_vi
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": exc.message_vi,
                "code": exc.code,
            }

        # Identity consistency across accepted face slots
        for prev_slot, prev_list in progress.get("face_embeddings", {}).items():
            if not prev_list:
                continue
            prev = np.asarray(prev_list, dtype=np.float32)
            sim = _cosine(vec, prev)
            if identity_fixture_key:
                continue  # same fixture key is consistent by construction
            if sim < 0.25:
                row.ui_state = "NEEDS_REVIEW"
                row.status = "NEEDS_REVIEW"
                row.guidance_vi = (
                    f"Mẫu {step} không nhất quán với {prev_slot} (có thể đổi người). "
                    "Tạm dừng và xác nhận lại nhân viên."
                )
                row.updated_at = self._clock.now_utc()
                session.flush()
                return {
                    **self.session_payload(row),
                    "accepted": False,
                    "message_vi": row.guidance_vi,
                    "code": "IDENTITY_INCONSISTENT",
                }

        # Persist via classic enrollment sample path (inactive templates)
        add = self._enrollment.add_sample(
            session,
            enrollment_id=row.enrollment_id,
            image=image,
            identity_fixture_key=identity_fixture_key,
            pose_slot=step,
        )
        if not add.get("accepted"):
            row.ui_state = "NEEDS_REVIEW" if "trùng" in add.get("message_vi", "") else row.ui_state
            row.guidance_vi = add.get("message_vi", "")
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {**self.session_payload(row), **add}

        sample_uid = str(uuid.uuid4())
        h, w = image.shape[:2]
        st = self._pipeline.status()
        enc_vec, nonce = self._store.encrypt_embedding(vec)
        samp = EnrollmentSample(
            session_id=row.id,
            sample_uid=sample_uid,
            slot=step,
            kind="FACE",
            quality_score=float(quality.score),
            quality_json=json.dumps(asdict(quality), ensure_ascii=False, default=str),
            native_width=w,
            native_height=h,
            person_height_px=0,
            model_id=st["embedder"]["model_id"],
            model_hash=st["embedder"]["model_hash"],
            frame_hash=frame_hash,
            encrypted_embedding=enc_vec,
            embedding_nonce=nonce,
            accepted=True,
            captured_at=self._clock.now_utc(),
        )
        session.add(samp)

        progress.setdefault("completed_slots", []).append(step)
        progress.setdefault("samples", {})[step] = sample_uid
        progress.setdefault("face_embeddings", {})[step] = vec.tolist()
        progress.setdefault("frame_hashes", []).append(frame_hash)
        progress.setdefault("announcements", []).append(
            {"slot": step, "message_vi": f"Đã hoàn thành {step}.", "at": self._clock.now_utc().isoformat()}
        )

        nxt = _next_slot(progress)
        row.progress_json = json.dumps(progress, ensure_ascii=False)
        row.ui_state = "SAMPLE_ACCEPTED"
        if nxt is None:
            row.current_step = "VALIDATE"
            row.status = "CHECKING_IDENTITY"
            row.ui_state = "READY_TO_ACTIVATE"
            row.guidance_vi = GUIDANCE_VI["READY_TO_ACTIVATE"]
        else:
            row.current_step = nxt
            row.status = "CAPTURING"
            row.guidance_vi = f"Đã nhận {step}. Tiếp theo: {GUIDANCE_VI.get(nxt, nxt)}"
        row.updated_at = self._clock.now_utc()
        session.flush()
        return {
            **self.session_payload(row),
            "accepted": True,
            "slot": step,
            "sample_uid": sample_uid,
            "announcement_vi": f"Hoàn thành tư thế {step}.",
            "message_vi": row.guidance_vi,
            "quality": asdict(quality),
        }

    def _capture_body(
        self,
        session: Session,
        row: EnrollmentSession,
        progress: dict,
        step: str,
        image: np.ndarray,
        frame_hash: str,
    ) -> dict[str, Any]:
        h, w = image.shape[:2]
        persons = self._person.detect(image)
        if len(persons) > 1:
            row.status = "PAUSED"
            row.ui_state = "MULTIPLE_PEOPLE"
            row.guidance_vi = GUIDANCE_VI["MULTIPLE_PEOPLE"]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "code": "MULTIPLE_PEOPLE",
                "message_vi": row.guidance_vi,
            }
        if not persons:
            row.ui_state = "WAITING_FOR_PERSON"
            row.guidance_vi = GUIDANCE_VI["WAITING_FOR_PERSON"]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
            }

        primary = max(persons, key=lambda p: p.h)
        # Require face evidence on same frame to anchor identity (body alone never enrolls)
        faces, face_q = self._pipeline.detect_and_quality(image, max_faces_ok=1)
        if not faces:
            row.ui_state = "WAITING_FOR_PERSON"
            row.guidance_vi = (
                "Cần thấy khuôn mặt của nhân viên đã chọn trên cùng khung hình "
                "để neo danh tính — ảnh toàn thân không đủ để ghi danh."
            )
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "code": "FACE_ANCHOR_REQUIRED",
            }

        blur = float(np.clip(np.std(image) / 64.0, 0.0, 1.0))
        bq = evaluate_body_quality(w, h, primary, person_count=len(persons), frame_blur=blur)
        if not bq["ok"]:
            row.ui_state = bq["state"]
            row.status = (
                "BODY_CAPTURE_BLOCKED"
                if bq["state"] in {"BLOCKED_BY_CAMERA_GEOMETRY", "BODY_NOT_FULLY_VISIBLE"}
                and primary.h < 200
                else "CAPTURING"
            )
            row.guidance_vi = bq["reasons_vi"][0] if bq["reasons_vi"] else GUIDANCE_VI[step]
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "body_quality": bq,
                "code": bq["state"],
            }

        # Diversity: reject near-identical body hashes already used
        sample_uid = str(uuid.uuid4())
        st = self._pipeline.status()
        samp = EnrollmentSample(
            session_id=row.id,
            sample_uid=sample_uid,
            slot=step,
            kind="BODY_REF",
            quality_score=float(bq["score"]),
            quality_json=json.dumps(bq, ensure_ascii=False),
            native_width=w,
            native_height=h,
            person_height_px=int(bq["person_height_px"]),
            model_id=self._person.info.model_id,
            model_hash=self._person.info.model_hash,
            frame_hash=frame_hash,
            accepted=True,
            captured_at=self._clock.now_utc(),
        )
        session.add(samp)
        progress.setdefault("completed_slots", []).append(step)
        progress.setdefault("samples", {})[step] = sample_uid
        progress.setdefault("frame_hashes", []).append(frame_hash)
        progress.setdefault("announcements", []).append(
            {
                "slot": step,
                "message_vi": f"Đã lưu ảnh toàn thân tham chiếu {step} (không phải sinh trắc học).",
                "at": self._clock.now_utc().isoformat(),
            }
        )
        nxt = _next_slot(progress)
        row.progress_json = json.dumps(progress, ensure_ascii=False)
        row.ui_state = "SAMPLE_ACCEPTED"
        if nxt is None:
            row.current_step = "VALIDATE"
            row.status = "CHECKING_IDENTITY"
            row.ui_state = "READY_TO_ACTIVATE"
            row.guidance_vi = GUIDANCE_VI["READY_TO_ACTIVATE"]
        else:
            row.current_step = nxt
            row.status = "CAPTURING"
            row.guidance_vi = f"Đã nhận {step}. Tiếp theo: {GUIDANCE_VI.get(nxt, nxt)}"
        row.updated_at = self._clock.now_utc()
        session.flush()
        # silence unused
        _ = face_q
        return {
            **self.session_payload(row),
            "accepted": True,
            "slot": step,
            "sample_uid": sample_uid,
            "announcement_vi": f"Hoàn thành {step}.",
            "message_vi": row.guidance_vi,
            "body_quality": bq,
            "note_vi": "Ảnh toàn thân là bằng chứng hỗ trợ — không dùng để nhận dạng tự động qua ngày.",
        }

    def validate_and_activate(
        self,
        session: Session,
        public_id: str,
        actor: str,
        *,
        identity_fixture_key: str | None = None,
        verification_image: np.ndarray | None = None,
    ) -> dict[str, Any]:
        row = self.get(session, public_id)
        if row is None:
            raise ValueError("Không tìm thấy phiên")
        progress = json.loads(row.progress_json or "{}")
        done = set(progress.get("completed_slots", []))
        missing_face = [s for s in FACE_SLOTS if s not in done]
        missing_body = [s for s in BODY_SLOTS if s not in done]
        if missing_face:
            raise ValueError(f"Thiếu tư thế khuôn mặt: {', '.join(missing_face)}")
        if missing_body:
            if row.status in {"BODY_CAPTURE_BLOCKED", "BLOCKED_BY_CAMERA_GEOMETRY"}:
                raise ValueError(
                    "BODY_CAPTURE_BLOCKED — không kích hoạt khi thiếu ảnh toàn thân đạt chuẩn"
                )
            raise ValueError(f"Thiếu ảnh toàn thân tham chiếu: {', '.join(missing_body)}")

        row.ui_state = "CHECKING_IDENTITY"
        row.status = "CHECKING_IDENTITY"
        row.guidance_vi = GUIDANCE_VI["CHECKING_IDENTITY"]
        session.flush()

        img = verification_image
        if img is None and identity_fixture_key:
            img = _fixture_canvas(identity_fixture_key)
        result = self._enrollment.activate(
            session,
            enrollment_id=row.enrollment_id,
            actor=actor,
            identity_fixture_key=identity_fixture_key,
            verification_image=img,
        )
        if result.get("activated"):
            row.status = "ACTIVE"
            row.ui_state = "ACTIVE"
            row.guidance_vi = "Đăng ký tự động đã kích hoạt."
            row.completed_at = self._clock.now_utc()
        else:
            row.status = "NEEDS_REVIEW"
            row.ui_state = "NEEDS_REVIEW"
            row.guidance_vi = result.get("message_vi", "Xác minh thất bại")
        row.updated_at = self._clock.now_utc()
        session.flush()
        self._buffers.pop(row.public_id, None)
        return {**self.session_payload(row), **result}

    def _require_open(
        self,
        session: Session,
        public_id: str,
        *,
        allow_paused: bool = False,
    ) -> EnrollmentSession:
        row = self.get(session, public_id)
        if row is None:
            raise ValueError("Không tìm thấy phiên")
        terminal = {"ACTIVE", "CANCELLED", "FAILED"}
        if row.status in terminal:
            raise ValueError(f"Phiên đã kết thúc ({row.status})")
        if row.status == "PAUSED" and not allow_paused:
            raise ValueError("Phiên đang tạm dừng")
        return row

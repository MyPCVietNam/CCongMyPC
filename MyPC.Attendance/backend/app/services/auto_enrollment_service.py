"""P01.5-HF guided automatic enrollment — no plaintext embeddings in progress_json."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.settings import AppSettings
from app.models.biometric import EnrollmentSample, EnrollmentSession
from app.models.entities import AuditLog
from app.services.enrollment_service import EnrollmentService, _fixture_canvas
from app.services.progress_sanitize import progress_contains_forbidden, scrub_progress
from app.vision.body.person_detector import PersonDetector, evaluate_body_quality
from app.vision.faces.embedder import EmbeddingError
from app.vision.faces.pipeline import FacePipeline
from app.vision.faces.quality import estimate_pose_from_landmarks
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.faces.types import MatchOutcome

FACE_SLOTS = ("FACE_FRONT", "FACE_LEFT", "FACE_RIGHT")
BODY_SLOTS = ("BODY_FRONT", "BODY_LEFT", "BODY_RIGHT", "BODY_MOTION")
ALL_SLOTS = FACE_SLOTS + BODY_SLOTS

# Pose acceptance: production requires confidence-qualified slot match (UNKNOWN cannot fill LEFT/RIGHT)
POSE_CONFIDENCE_MIN = 0.45
NEAR_DUP_EMBED_SIM = 0.985

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


def _capture_origin_for_source(source: str) -> str:
    s = (source or "").upper()
    if s in {"DEMO", "SYNTHETIC", "SYNTHETIC_TEST"}:
        return "SYNTHETIC_TEST"
    if s in {"UPLOAD", "AUTHORIZED_UPLOAD"}:
        return "AUTHORIZED_UPLOAD"
    if s in {"REAL_CAMERA", "CAMERA_LIVE", "LIVE"}:
        return "CAMERA_LIVE"
    return "SYNTHETIC_TEST" if s == "AUTO" else s or "SYNTHETIC_TEST"


def _frame_perceptual_hash(image: np.ndarray) -> str:
    """
    Combine average-hash (near-duplicate detection) with a content digest of the
    center crop so distinct DEMO canvases and real frames do not collide.
    """
    small = cv2.resize(image, (16, 16), interpolation=cv2.INTER_AREA)
    if small.ndim == 3:
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    else:
        gray = small
    mean = float(np.mean(gray))
    bits = "".join("1" if float(v) >= mean else "0" for v in gray.flatten())
    h, w = image.shape[:2]
    y0, y1 = h // 4, 3 * h // 4
    x0, x1 = w // 4, 3 * w // 4
    center = image[y0:y1:7, x0:x1:7]
    content = hashlib.sha256(center.tobytes()).hexdigest()[:24]
    return hashlib.sha256(f"{bits}:{content}".encode()).hexdigest()[:32]


class AutoEnrollmentService:
    def __init__(
        self,
        clock: Clock,
        pipeline: FacePipeline,
        store: FaceTemplateStore,
        enrollment_service: EnrollmentService,
        person_detector: PersonDetector | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self._clock = clock
        self._pipeline = pipeline
        self._store = store
        self._enrollment = enrollment_service
        self._person = person_detector or PersonDetector()
        self._settings = settings or AppSettings()
        # Ephemeral RAM only — discarded on restart; never written to SQLite
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._ram_embeddings: dict[str, dict[str, np.ndarray]] = {}

    def start(
        self,
        session: Session,
        *,
        employee_id: int,
        operator: str,
        authorization_ref: str,
        authorization_ack_vi: str,
        source: str = "DEMO",
        camera_id: int | None = None,
        bound_profile: str = "",
        bound_config_revision: str = "",
        camera_lab_approval_id: str = "",
    ) -> EnrollmentSession:
        capture_origin = _capture_origin_for_source(source)
        # Preserve provenance — never remapp DEMO → AUTO
        enrollment_source = source if source else "DEMO"
        src_u = enrollment_source.upper()
        if src_u == "REAL_CAMERA":
            if camera_id is None:
                raise ValueError("REAL_CAMERA yêu cầu camera_id — gắn bất biến tại lúc bắt đầu.")
            if not (bound_config_revision and camera_lab_approval_id):
                raise ValueError(
                    "REAL_CAMERA yêu cầu config_revision + CAMERA_LAB approval đã ký trên server."
                )
        elif camera_id is not None:
            raise ValueError("Không gắn camera LIVE cho phiên DEMO/UPLOAD.")
        enr = self._enrollment.start_enrollment(
            session,
            employee_id=employee_id,
            enrolled_by=operator,
            authorization_ref=authorization_ref,
            authorization_ack_vi=authorization_ack_vi,
            source=enrollment_source,
        )
        now = self._clock.now_utc()
        st = self._pipeline.status()
        progress = scrub_progress(
            {
                "completed_slots": [],
                "samples": {},
                "frame_hashes": [],
                "announcements": [],
                "quality_scores": {},
                "capture_origin": capture_origin,
                "algorithm_backend": (
                    "OPENCV_REAL"
                    if self._pipeline.embedder.info.backend == "opencv_dnn"
                    else "SYNTHETIC_FIXTURE"
                ),
                "testing_mode": capture_origin == "SYNTHETIC_TEST",
                "model_id": st["embedder"]["model_id"],
                "model_hash": st["embedder"]["model_hash"],
                "bound_camera_id": camera_id,
                "bound_config_revision": bound_config_revision or "",
            }
        )
        assert not progress_contains_forbidden(progress)
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
            source=enrollment_source,
            camera_id=camera_id,
            bound_profile=bound_profile or "",
            bound_config_revision=bound_config_revision or "",
            camera_lab_approval_id=camera_lab_approval_id or "",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        self._buffers[row.public_id] = []
        self._ram_embeddings[row.public_id] = {}
        session.add(
            AuditLog(
                actor=operator,
                action="biometric.auto_enrollment.start",
                entity_type="enrollment_session",
                entity_id=row.public_id,
                reason=(
                    f"{authorization_ref}|origin={capture_origin}|src={enrollment_source}"
                    f"|cam={camera_id}|apr={camera_lab_approval_id}"
                ),
                timestamp=now,
            )
        )
        return row

    def get(self, session: Session, public_id: str) -> EnrollmentSession | None:
        return session.scalar(
            select(EnrollmentSession).where(EnrollmentSession.public_id == public_id)
        )

    def session_payload(self, row: EnrollmentSession) -> dict[str, Any]:
        progress = scrub_progress(json.loads(row.progress_json or "{}"))
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
            "camera_id": row.camera_id,
            "bound_profile": row.bound_profile or "",
            "bound_config_revision": row.bound_config_revision or "",
            "camera_lab_approval_id": row.camera_lab_approval_id or "",
            "capture_origin": progress.get("capture_origin"),
            "algorithm_backend": progress.get("algorithm_backend"),
            "testing_mode": progress.get("testing_mode", False),
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
        self._ram_embeddings.pop(row.public_id, None)
        session.flush()
        return row

    def retry_step(self, session: Session, public_id: str, slot: str | None = None) -> EnrollmentSession:
        row = self._require_open(session, public_id, allow_paused=True)
        progress = scrub_progress(json.loads(row.progress_json or "{}"))
        target = slot or row.current_step
        if target in progress.get("completed_slots", []):
            progress["completed_slots"] = [s for s in progress["completed_slots"] if s != target]
            progress.get("samples", {}).pop(target, None)
            progress.get("quality_scores", {}).pop(target, None)
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
                # Best-effort wipe ciphertext (not secure deletion of WAL/backups)
                if s.encrypted_embedding is not None:
                    s.encrypted_embedding = b"\0" * len(s.encrypted_embedding)
                if s.encrypted_image is not None:
                    s.encrypted_image = b"\0" * len(s.encrypted_image)
        self._ram_embeddings.setdefault(row.public_id, {}).pop(target, None)
        row.current_step = target
        row.status = "CAPTURING"
        row.ui_state = target
        row.guidance_vi = GUIDANCE_VI.get(target, "")
        row.progress_json = json.dumps(scrub_progress(progress), ensure_ascii=False)
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
        capture_origin_override: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_open(session, public_id)
        if row.status == "PAUSED":
            return {**self.session_payload(row), "accepted": False, "message_vi": "Phiên đang tạm dừng."}

        self._enforce_synthetic_policy(identity_fixture_key=identity_fixture_key, force_slot=force_slot)

        progress = scrub_progress(json.loads(row.progress_json or "{}"))
        step = force_slot or row.current_step or _next_slot(progress) or "FACE_FRONT"
        if force_slot and not self._settings.force_slot_allowed():
            raise PermissionError("force_slot bị từ chối ngoài môi trường kiểm thử.")

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

        frame_hash = _frame_perceptual_hash(image)
        if frame_hash in progress.get("frame_hashes", [])[-40:]:
            row.ui_state = "WAITING_FOR_PERSON"
            row.guidance_vi = "Khung hình trùng/gần trùng — hãy đổi tư thế rồi thử lại."
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

    def _enforce_synthetic_policy(
        self,
        *,
        identity_fixture_key: str | None,
        force_slot: str | None,
    ) -> None:
        if identity_fixture_key and not self._settings.synthetic_fixtures_allowed():
            raise PermissionError(
                "identity_fixture_key bị từ chối trong production — không dùng fixture để tạo danh tính thật."
            )
        if force_slot and not self._settings.force_slot_allowed():
            raise PermissionError("force_slot chỉ được phép trong môi trường kiểm thử tường minh.")

    def _load_slot_embeddings(self, session: Session, row: EnrollmentSession) -> dict[str, np.ndarray]:
        """Decrypt accepted face samples in memory; prefer RAM cache, never persist plaintext."""
        cached = self._ram_embeddings.setdefault(row.public_id, {})
        if cached:
            return dict(cached)
        rows = session.scalars(
            select(EnrollmentSample).where(
                EnrollmentSample.session_id == row.id,
                EnrollmentSample.kind == "FACE",
                EnrollmentSample.accepted.is_(True),
                EnrollmentSample.replaced.is_(False),
            )
        ).all()
        out: dict[str, np.ndarray] = {}
        for s in rows:
            if s.encrypted_embedding is None or s.embedding_nonce is None:
                continue
            vec = self._store.decrypt_embedding(s.encrypted_embedding, s.embedding_nonce)
            out[s.slot] = vec
            cached[s.slot] = vec
        return out

    def _pose_accepted(self, step: str, pose_slot_hint: str | None, confidence: float, *, testing: bool) -> bool:
        if testing:
            # DEMO/fixture may advance slots under operator force; still prefer matching hint
            return True
        if confidence < POSE_CONFIDENCE_MIN:
            return False
        if step == "FACE_FRONT":
            return pose_slot_hint == "FACE_FRONT"
        if step in {"FACE_LEFT", "FACE_RIGHT"}:
            # UNKNOWN must NOT satisfy LEFT/RIGHT in production
            return pose_slot_hint == step
        return False

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
        testing = bool(progress.get("testing_mode")) or bool(identity_fixture_key)
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
            if quality.pose:
                quality.pose.slot_hint = step
                quality.pose.confidence = max(quality.pose.confidence, 0.7)

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
            if quality.pose and step in {"FACE_LEFT", "FACE_RIGHT"}:
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

        pose = quality.pose or estimate_pose_from_landmarks(max(faces, key=lambda f: f.w * f.h))
        if not self._pose_accepted(step, pose.slot_hint if pose else None, pose.confidence if pose else 0.0, testing=testing):
            row.ui_state = "TURN_LEFT" if step == "FACE_LEFT" else ("TURN_RIGHT" if step == "FACE_RIGHT" else "WAITING_FOR_PERSON")
            row.guidance_vi = (
                f"Tư thế chưa đạt cho {step} (ước lượng: {pose.slot_hint if pose else 'UNKNOWN'}, "
                f"độ tin cậy {pose.confidence if pose else 0:.2f}). {GUIDANCE_VI[step]}"
            )
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": row.guidance_vi,
                "code": "POSE_NOT_DISTINCT",
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

        # Identity consistency via decrypted prior samples (RAM), never from progress_json
        prior = self._load_slot_embeddings(session, row)
        for prev_slot, prev in prior.items():
            sim = _cosine(vec, prev)
            if identity_fixture_key:
                continue
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
            if sim >= NEAR_DUP_EMBED_SIM and prev_slot != step:
                row.guidance_vi = "Mẫu gần trùng tư thế trước — hãy xoay mặt rõ hơn."
                row.updated_at = self._clock.now_utc()
                session.flush()
                return {
                    **self.session_payload(row),
                    "accepted": False,
                    "message_vi": row.guidance_vi,
                    "code": "NEAR_DUPLICATE_POSE",
                }

        add = self._enrollment.add_sample(
            session,
            enrollment_id=row.enrollment_id,
            image=image,
            identity_fixture_key=identity_fixture_key,
            pose_slot=step,
        )
        if not add.get("accepted"):
            row.guidance_vi = add.get("message_vi", "")
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {**self.session_payload(row), **add}

        sample_uid = str(uuid.uuid4())
        h, w = image.shape[:2]
        st = self._pipeline.status()
        enc_vec, nonce = self._store.encrypt_embedding(vec)
        # Also store a small encrypted face crop thumbnail for authorized review (not full store)
        x2, y2 = min(w, primary.x + primary.w), min(h, primary.y + primary.h)
        crop = image[max(0, primary.y) : y2, max(0, primary.x) : x2]
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        enc_img = nonce_img = None
        if ok:
            enc_img, nonce_img = self._store.encrypt_image(buf.tobytes(), aad=b"mypc-face-crop-v1")
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
            encrypted_image=enc_img,
            image_nonce=nonce_img,
            accepted=True,
            captured_at=self._clock.now_utc(),
        )
        session.add(samp)
        self._ram_embeddings.setdefault(row.public_id, {})[step] = vec

        progress.setdefault("completed_slots", []).append(step)
        progress.setdefault("samples", {})[step] = sample_uid
        progress.setdefault("quality_scores", {})[step] = float(quality.score)
        progress.setdefault("frame_hashes", []).append(frame_hash)
        progress.setdefault("announcements", []).append(
            {"slot": step, "message_vi": f"Đã hoàn thành {step}.", "at": self._clock.now_utc().isoformat()}
        )
        # CRITICAL: never write face_embeddings into progress
        progress.pop("face_embeddings", None)
        progress = scrub_progress(progress)
        assert not progress_contains_forbidden(progress)

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

    def _encode_person_crop(self, image: np.ndarray, box) -> bytes | None:
        h, w = image.shape[:2]
        x2, y2 = min(w, box.x + box.w), min(h, box.y + box.h)
        crop = image[max(0, box.y) : y2, max(0, box.x) : x2]
        if crop.size == 0:
            return None
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return buf.tobytes() if ok else None

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

        # Production: synthetic person detector cannot claim real BODY_CAPTURE_PASS
        if self._person.info.backend == "synthetic_fixture" and not progress.get("testing_mode"):
            row.status = "BODY_CAPTURE_BLOCKED"
            row.ui_state = "BODY_CAPTURE_BLOCKED"
            row.guidance_vi = (
                "Bộ phát hiện người thật chưa sẵn sàng (chưa có model đã kiểm chứng giấy phép/SHA256). "
                "Không lưu 4 ảnh toàn thân giả. Dùng quy trình upload được ủy quyền hoặc chờ CAMERA_LAB."
            )
            row.updated_at = self._clock.now_utc()
            session.flush()
            return {
                **self.session_payload(row),
                "accepted": False,
                "blocked": True,
                "code": "BODY_DETECTOR_NOT_READY",
                "message_vi": row.guidance_vi,
                "body_quality": bq,
            }

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

        crop_bytes = self._encode_person_crop(image, primary)
        if not crop_bytes:
            return {
                **self.session_payload(row),
                "accepted": False,
                "message_vi": "Không cắt được ảnh toàn thân hợp lệ.",
                "code": "BODY_CROP_FAILED",
            }
        enc_img, img_nonce = self._store.encrypt_image(crop_bytes)

        sample_uid = str(uuid.uuid4())
        samp = EnrollmentSample(
            session_id=row.id,
            sample_uid=sample_uid,
            slot=step,
            kind="BODY_REF",
            quality_score=float(bq["score"]),
            quality_json=json.dumps(
                {**bq, "detector_backend": self._person.info.backend, "supporting_reference_only": True},
                ensure_ascii=False,
            ),
            native_width=w,
            native_height=h,
            person_height_px=int(bq["person_height_px"]),
            model_id=self._person.info.model_id,
            model_hash=self._person.info.model_hash,
            frame_hash=frame_hash,
            encrypted_image=enc_img,
            image_nonce=img_nonce,
            accepted=True,
            captured_at=self._clock.now_utc(),
        )
        session.add(samp)
        progress.setdefault("completed_slots", []).append(step)
        progress.setdefault("samples", {})[step] = sample_uid
        progress.setdefault("quality_scores", {})[step] = float(bq["score"])
        progress.setdefault("frame_hashes", []).append(frame_hash)
        progress.setdefault("announcements", []).append(
            {
                "slot": step,
                "message_vi": f"Đã lưu ảnh toàn thân tham chiếu {step} (không phải sinh trắc học).",
                "at": self._clock.now_utc().isoformat(),
            }
        )
        progress = scrub_progress(progress)
        assert not progress_contains_forbidden(progress)
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
        _ = face_q
        return {
            **self.session_payload(row),
            "accepted": True,
            "slot": step,
            "sample_uid": sample_uid,
            "has_encrypted_image": True,
            "announcement_vi": f"Hoàn thành {step}.",
            "message_vi": row.guidance_vi,
            "body_quality": bq,
            "note_vi": "Ảnh toàn thân là bằng chứng hỗ trợ — không dùng để nhận dạng tự động qua ngày.",
        }

    def get_sample_image(
        self,
        session: Session,
        public_id: str,
        sample_uid: str,
    ) -> tuple[EnrollmentSample, bytes]:
        row = self.get(session, public_id)
        if row is None:
            raise ValueError("Không tìm thấy phiên")
        samp = session.scalar(
            select(EnrollmentSample).where(
                EnrollmentSample.session_id == row.id,
                EnrollmentSample.sample_uid == sample_uid,
                EnrollmentSample.replaced.is_(False),
            )
        )
        if samp is None or samp.encrypted_image is None or samp.image_nonce is None:
            raise ValueError("Không có ảnh mã hóa cho mẫu này")
        aad = b"mypc-face-crop-v1" if samp.kind == "FACE" else b"mypc-body-ref-v1"
        plain = self._store.decrypt_image(samp.encrypted_image, samp.image_nonce, aad=aad)
        return samp, plain

    def validate_and_activate(
        self,
        session: Session,
        public_id: str,
        actor: str,
        *,
        identity_fixture_key: str | None = None,
        verification_image: np.ndarray | None = None,
    ) -> dict[str, Any]:
        self._enforce_synthetic_policy(identity_fixture_key=identity_fixture_key, force_slot=None)
        row = self.get(session, public_id)
        if row is None:
            raise ValueError("Không tìm thấy phiên")
        progress = scrub_progress(json.loads(row.progress_json or "{}"))
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

        # Body samples must have encrypted blobs
        body_samples = session.scalars(
            select(EnrollmentSample).where(
                EnrollmentSample.session_id == row.id,
                EnrollmentSample.kind == "BODY_REF",
                EnrollmentSample.accepted.is_(True),
                EnrollmentSample.replaced.is_(False),
            )
        ).all()
        for s in body_samples:
            if not s.encrypted_image or not s.image_nonce:
                raise ValueError(
                    f"Mẫu {s.slot} thiếu ảnh mã hóa — không kích hoạt trên metadata-only."
                )

        row.ui_state = "CHECKING_IDENTITY"
        row.status = "CHECKING_IDENTITY"
        row.guidance_vi = GUIDANCE_VI["CHECKING_IDENTITY"]
        session.flush()

        # Independent verification: production requires a real image distinct from enrollment frames
        if not identity_fixture_key and verification_image is None:
            raise ValueError(
                "Cần khung hình xác minh độc lập (không dùng lại khung đã đăng ký)."
            )
        if identity_fixture_key and not self._settings.synthetic_fixtures_allowed():
            raise PermissionError("Fixture verification bị từ chối trong production.")

        img = verification_image
        if img is None and identity_fixture_key:
            img = _fixture_canvas(identity_fixture_key + "::verify")
        # Near-dup check vs enrollment perceptual hashes
        if verification_image is not None:
            vhash = _frame_perceptual_hash(verification_image)
            if vhash in progress.get("frame_hashes", []):
                raise ValueError("Ảnh xác minh trùng khung đăng ký — hãy thu khung độc lập.")

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
        row.progress_json = json.dumps(scrub_progress(json.loads(row.progress_json or "{}")), ensure_ascii=False)
        session.flush()
        self._buffers.pop(row.public_id, None)
        self._ram_embeddings.pop(row.public_id, None)
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

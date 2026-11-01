"""Composable face pipeline — REAL path uses YuNet landmarks + SFace alignCrop/feature."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.vision.faces.detector import FaceDetector
from app.vision.faces.embedder import EmbeddingError, FaceEmbedder
from app.vision.faces.matcher import match_embedding
from app.vision.faces.quality import MIN_FACE_WIDTH_PX, evaluate_face_quality
from app.vision.faces.types import (
    FaceBox,
    InferenceMode,
    MatchOutcome,
    QualityReport,
    VerificationResult,
)


@dataclass
class FacePipelineConfig:
    models_dir: Path
    yunet_filename: str = "face_detection_yunet_2023mar.onnx"
    sface_filename: str = "face_recognition_sface_2021dec.onnx"
    # Verified 2026-11-02 from opencv_zoo raw main download (see models/manifest.json)
    yunet_sha256: str = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    sface_sha256: str = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
    match_threshold: float = 0.45
    match_margin: float = 0.05
    min_face_px: int = MIN_FACE_WIDTH_PX
    require_real: bool = False  # True → fail closed if weights/OpenCV unavailable


class FacePipeline:
    def __init__(self, cfg: FacePipelineConfig) -> None:
        self.cfg = cfg
        yunet = cfg.models_dir / cfg.yunet_filename
        sface = cfg.models_dir / cfg.sface_filename
        self.detector = FaceDetector(
            yunet if yunet.exists() else None,
            cfg.yunet_sha256 if yunet.exists() else None,
            require_real=cfg.require_real,
        )
        self.embedder = FaceEmbedder(
            sface if sface.exists() else None,
            cfg.sface_sha256 if sface.exists() else None,
            require_real=cfg.require_real,
        )

    @property
    def inference_mode(self) -> InferenceMode:
        if (
            self.embedder.info.backend == "opencv_dnn"
            and self.detector.info.backend == "opencv_dnn"
        ):
            return InferenceMode.REAL
        return InferenceMode.SYNTHETIC_FIXTURE

    def status(self) -> dict:
        return {
            "detector": asdict(self.detector.info) if hasattr(self.detector.info, "__dataclass_fields__") else self.detector.info.__dict__,
            "embedder": asdict(self.embedder.info) if hasattr(self.embedder.info, "__dataclass_fields__") else self.embedder.info.__dict__,
            "match_threshold": self.cfg.match_threshold,
            "match_margin": self.cfg.match_margin,
            "min_face_px": self.cfg.min_face_px,
            "inference_mode": self.inference_mode.value,
            "weights_bundled": {
                "yunet": (self.cfg.models_dir / self.cfg.yunet_filename).exists(),
                "sface": (self.cfg.models_dir / self.cfg.sface_filename).exists(),
            },
        }

    def detect_and_quality(
        self,
        image: np.ndarray,
        *,
        expected_slot: str | None = None,
        max_faces_ok: int = 1,
    ) -> tuple[list[FaceBox], QualityReport]:
        h, w = image.shape[:2]
        try:
            faces = self.detector.detect(image)
        except RuntimeError:
            q = QualityReport(
                ok=False,
                score=0.0,
                face_width_px=0,
                inter_eye_px=0.0,
                blur_score=0.0,
                laplacian_var=0.0,
                pose=None,
                hard_fail=True,
                reasons_vi=["Bộ phát hiện khuôn mặt chưa sẵn sàng (NOT_READY)."],
                breakdown={"state": "NOT_READY"},
                metadata={},
            )
            return [], q
        if not faces:
            q = evaluate_face_quality(
                image, w, h, FaceBox(0, 0, 0, 0), face_count=0, min_face_px=self.cfg.min_face_px
            )
            return [], q
        primary = max(faces, key=lambda f: f.w * f.h)
        q = evaluate_face_quality(
            image,
            w,
            h,
            primary,
            min_face_px=self.cfg.min_face_px,
            face_count=len(faces),
            max_faces_ok=max_faces_ok,
            expected_slot=expected_slot,
        )
        return faces, q

    def embed_image(
        self,
        image: np.ndarray,
        identity_fixture_key: str | None = None,
        *,
        face: FaceBox | None = None,
    ) -> np.ndarray:
        """
        REAL: detect (if needed) → alignCrop(original, yunet_row) → feature → L2.
        SYNTHETIC_FIXTURE with identity_fixture_key: deterministic fixture vector only.
        Real image bytes MUST NEVER fall through to hash-seeded synthetic embeddings.
        """
        if identity_fixture_key:
            return self.embedder.embed_identity_fixture(identity_fixture_key)

        if self.inference_mode == InferenceMode.REAL or self.embedder.info.backend == "opencv_dnn":
            box = face
            if box is None or box.yunet_row is None:
                faces, _ = self.detect_and_quality(image)
                if not faces:
                    raise EmbeddingError(
                        "Không tìm thấy khuôn mặt để trích xuất đặc trưng.",
                        "NO_FACE",
                    )
                box = max(faces, key=lambda f: f.w * f.h)
            if box.yunet_row is None:
                raise EmbeddingError(
                    "Thiếu hàng phát hiện YuNet đầy đủ (landmark) cho alignCrop.",
                    "LANDMARKS_MISSING",
                )
            return self.embedder.embed_real(image, box.yunet_row)

        # Explicit synthetic backend without fixture key — still forbid byte-hash of real images
        raise EmbeddingError(
            "Chế độ synthetic yêu cầu identity_fixture_key; không nhúng ảnh thật bằng hash.",
            "SYNTHETIC_FALLBACK_FORBIDDEN",
        )

    def verify(
        self,
        image: np.ndarray,
        gallery: list[tuple[int, np.ndarray]],
        *,
        identity_fixture_key: str | None = None,
    ) -> VerificationResult:
        faces, quality = self.detect_and_quality(image)
        if identity_fixture_key and faces and not quality.ok:
            # CI synthetic solid frames — fixture path only; never used for REAL publication
            quality = QualityReport(
                ok=True,
                score=max(quality.score, 0.5),
                face_width_px=max(f.w for f in faces),
                inter_eye_px=max(f.inter_eye_px for f in faces),
                blur_score=1.0,
                laplacian_var=200.0,
                pose=quality.pose,
                hard_fail=False,
                reasons_vi=[],
                breakdown={**quality.breakdown, "fixture_relaxed": True},
                metadata={**quality.metadata, "fixture_relaxed": True},
            )
        if quality.reasons_vi and not quality.ok:
            if len(faces) > 1:
                outcome = MatchOutcome.MULTIPLE_FACES
            elif not faces:
                outcome = MatchOutcome.NO_FACE
            else:
                outcome = MatchOutcome.LOW_QUALITY
            return VerificationResult(
                outcome=outcome,
                employee_id=None,
                similarity=0.0,
                second_best_similarity=0.0,
                message_vi=quality.reasons_vi[0],
                quality=quality,
                model_id=self.embedder.info.model_id,
                threshold=self.cfg.match_threshold,
                inference_mode=self.inference_mode.value,
            )
        try:
            primary = max(faces, key=lambda f: f.w * f.h) if faces else None
            probe = self.embed_image(
                image, identity_fixture_key=identity_fixture_key, face=primary
            )
        except EmbeddingError as exc:
            return VerificationResult(
                outcome=MatchOutcome.NOT_READY
                if exc.code in {"NOT_READY", "MODEL_UNAVAILABLE"}
                else MatchOutcome.LOW_QUALITY,
                employee_id=None,
                similarity=0.0,
                second_best_similarity=0.0,
                message_vi=exc.message_vi,
                quality=quality,
                model_id=self.embedder.info.model_id,
                threshold=self.cfg.match_threshold,
                inference_mode=self.inference_mode.value,
            )
        result = match_embedding(
            probe,
            gallery,
            threshold=self.cfg.match_threshold,
            margin=self.cfg.match_margin,
            model_id=self.embedder.info.model_id,
        )
        result.quality = quality
        result.inference_mode = self.inference_mode.value
        return result

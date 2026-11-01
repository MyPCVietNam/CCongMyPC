"""YuNet detector — preserves full detection rows for SFace alignCrop."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.vision.faces.types import FaceBox, InferenceMode


@dataclass
class DetectorInfo:
    model_id: str
    model_hash: str
    backend: str
    ready: bool
    inference_mode: str = InferenceMode.SYNTHETIC_FIXTURE.value


class FaceDetector:
    def __init__(
        self,
        model_path: Path | None,
        expected_sha256: str | None = None,
        *,
        require_real: bool = False,
    ) -> None:
        self._path = model_path
        self._expected = (expected_sha256 or "").lower()
        self._require_real = require_real
        self._det = None
        self.info = DetectorInfo(
            "yunet_2023mar",
            "PENDING",
            "unavailable",
            False,
            InferenceMode.REAL.value if require_real else InferenceMode.SYNTHETIC_FIXTURE.value,
        )
        self._try_load()

    def _try_load(self) -> None:
        if self._path is None or not self._path.exists():
            if self._require_real:
                self.info = DetectorInfo(
                    "yunet_2023mar",
                    "MISSING",
                    "unavailable",
                    False,
                    InferenceMode.REAL.value,
                )
                return
            self.info = DetectorInfo(
                "synthetic_fixture_v1",
                "SYNTHETIC",
                "synthetic_fixture",
                True,
                InferenceMode.SYNTHETIC_FIXTURE.value,
            )
            return
        data = self._path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if self._expected and self._expected not in {"", "pending_download_verify"} and digest != self._expected:
            raise ValueError(f"YuNet SHA256 mismatch: got {digest}, expected {self._expected}")
        try:
            import cv2  # type: ignore

            self._det = cv2.FaceDetectorYN.create(str(self._path), "", (320, 320))
            self.info = DetectorInfo(
                "yunet_2023mar",
                digest,
                "opencv_dnn",
                True,
                InferenceMode.REAL.value,
            )
        except Exception:
            if self._require_real:
                self.info = DetectorInfo(
                    "yunet_2023mar",
                    digest,
                    "unavailable",
                    False,
                    InferenceMode.REAL.value,
                )
                return
            self.info = DetectorInfo(
                "yunet_2023mar",
                digest,
                "synthetic_fixture",
                True,
                InferenceMode.SYNTHETIC_FIXTURE.value,
            )

    def detect(self, image: np.ndarray) -> list[FaceBox]:
        h, w = image.shape[:2]
        if self._det is not None:
            self._det.setInputSize((w, h))
            _, faces = self._det.detect(image)
            out: list[FaceBox] = []
            if faces is not None:
                for f in faces:
                    row = np.asarray(f, dtype=np.float32).reshape(-1)
                    x, y, bw, bh = [int(round(v)) for v in row[:4]]
                    score = float(row[-1]) if row.size > 14 else float(row[4]) if row.size > 4 else 1.0
                    landmarks: list[tuple[float, float]] = []
                    # YuNet: x,y,w,h, right_eye_x, right_eye_y, left_eye_x, left_eye_y,
                    # nose_x, nose_y, right_mouth_x, right_mouth_y, left_mouth_x, left_mouth_y, score
                    if row.size >= 14:
                        for i in range(4, 14, 2):
                            landmarks.append((float(row[i]), float(row[i + 1])))
                    out.append(
                        FaceBox(
                            x=x,
                            y=y,
                            w=bw,
                            h=bh,
                            score=score,
                            landmarks=landmarks,
                            yunet_row=row.copy(),
                        )
                    )
            return out

        if self._require_real or self.info.backend == "unavailable":
            raise RuntimeError("YuNet detector not ready for REAL inference")

        # Synthetic fixture: centered face with approximate landmarks
        if image.size == 0:
            return []
        mean = float(np.mean(image))
        if mean < 5:
            return []
        fw, fh = max(120, w // 4), max(120, h // 4)
        x = (w - fw) // 2
        y = (h - fh) // 2
        # Synthetic landmarks (right eye, left eye, nose, right mouth, left mouth) in image coords
        re = (x + fw * 0.35, y + fh * 0.38)
        le = (x + fw * 0.65, y + fh * 0.38)
        nose = (x + fw * 0.50, y + fh * 0.55)
        rm = (x + fw * 0.38, y + fh * 0.72)
        lm = (x + fw * 0.62, y + fh * 0.72)
        row = np.array(
            [x, y, fw, fh, re[0], re[1], le[0], le[1], nose[0], nose[1], rm[0], rm[1], lm[0], lm[1], 0.99],
            dtype=np.float32,
        )
        return [
            FaceBox(
                x=x,
                y=y,
                w=fw,
                h=fh,
                score=0.99,
                landmarks=[re, le, nose, rm, lm],
                yunet_row=row,
            )
        ]

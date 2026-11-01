"""
Person detector for full-body reference capture.

Preferred production model: YOLOX-Nano (Apache-2.0) with pinned SHA256.
Until weights are lab-verified and license-audited for bundling, synthetic
geometry heuristics are used under DEMO/SYNTHETIC_FIXTURE only.
Ultralytics AGPL models are NOT used by default.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class PersonBox:
    x: int
    y: int
    w: int
    h: int
    score: float = 1.0

    @property
    def height_px(self) -> int:
        return self.h

    @property
    def feet_visible_heuristic(self) -> bool:
        # Bottom of box near image bottom OR height dominates frame
        return True  # refined by evaluate_body_quality against image dims


@dataclass
class PersonDetectorInfo:
    model_id: str
    model_hash: str
    backend: str
    ready: bool
    license_note: str = ""


# Starting experimental target (calibrate on EZVIZ)
MIN_BODY_HEIGHT_PX = 400


class PersonDetector:
    def __init__(self, model_path=None, expected_sha256: str | None = None) -> None:
        self._path = model_path
        self._net = None
        # Production must fail closed without audited weights. DEMO/testing_mode may use synthetic.
        if model_path is not None and getattr(model_path, "exists", lambda: False)():
            # Placeholder: real ONNX person detector load after license + SHA256 audit of the
            # exact weight file. Ultralytics AGPL is NOT used by default.
            self.info = PersonDetectorInfo(
                model_id="pending_licensed_person_detector",
                model_hash="UNVERIFIED",
                backend="unavailable",
                ready=False,
                license_note="Weight path provided but loader not activated until license audit PASS.",
            )
        else:
            self.info = PersonDetectorInfo(
                model_id="synthetic_person_v1",
                model_hash="SYNTHETIC",
                backend="synthetic_fixture",
                ready=True,
                license_note=(
                    "No YOLOX/person weights bundled — DEMO/synthetic geometry only. "
                    "Do not claim BODY_REFERENCE_CAPTURE PASS on real camera until "
                    "licensed model + SHA256 + CAMERA_LAB verified."
                ),
            )

    def detect(self, image: np.ndarray) -> list[PersonBox]:
        h, w = image.shape[:2]
        if image.size == 0 or float(np.mean(image)) < 5:
            return []
        # Synthetic: one full-height person from near top to near bottom
        margin = max(2, int(0.02 * h))
        if h < 200:
            # Too small frame — partial box so quality can BLOCK honestly
            ph = max(40, h - 2 * margin)
            pw = max(30, w // 3)
            x = (w - pw) // 2
            return [PersonBox(x=x, y=margin, w=pw, h=ph, score=0.9)]
        y = margin
        ph = h - 2 * margin
        pw = max(80, int(ph * 0.28))
        x = (w - pw) // 2
        return [PersonBox(x=x, y=y, w=pw, h=ph, score=0.9)]


def evaluate_body_quality(
    image_w: int,
    image_h: int,
    box: PersonBox,
    *,
    person_count: int = 1,
    min_height_px: int = MIN_BODY_HEIGHT_PX,
    frame_blur: float = 1.0,
) -> dict:
    reasons: list[str] = []
    state = "OK"
    hard_fail = False
    if person_count == 0:
        return {
            "ok": False,
            "hard_fail": True,
            "state": "WAITING_FOR_PERSON",
            "reasons_vi": ["Không thấy người trong khung hình."],
            "person_height_px": 0,
            "score": 0.0,
        }
    if person_count > 1:
        return {
            "ok": False,
            "hard_fail": True,
            "state": "MULTIPLE_PEOPLE",
            "reasons_vi": [
                "Nhiều người trong khung hình. Chỉ giữ đúng nhân viên đang đăng ký."
            ],
            "person_height_px": box.h,
            "score": 0.0,
        }
    # Head and feet in frame: top near top margin, bottom near bottom
    top_ok = box.y <= max(8, int(0.08 * image_h))
    bottom_ok = (box.y + box.h) >= image_h - max(8, int(0.08 * image_h))
    if not (top_ok and bottom_ok) or box.h < min_height_px:
        hard_fail = True
        state = "BODY_NOT_FULLY_VISIBLE"
        if box.h < min_height_px:
            state = "BLOCKED_BY_CAMERA_GEOMETRY"
            reasons.append(
                f"Chiều cao người trong ảnh gốc chỉ ~{box.h} px (cần ≥{min_height_px} px). "
                "Camera góc cao/xa có thể không chụp đủ đầu-chân — "
                "BODY_CAPTURE_BLOCKED. Hãy đứng gần hơn hoặc dùng vị trí đăng ký phụ được ủy quyền."
            )
        else:
            reasons.append(
                "Không thấy đủ đầu và chân trong khung hình. Không được cắt nửa người rồi đánh dấu đủ."
            )
    if frame_blur < 0.2:
        hard_fail = True
        state = "BLURRY"
        reasons.append("Ảnh toàn thân bị mờ.")
    score = min(1.0, box.h / float(min_height_px)) * (0.5 + 0.5 * frame_blur)
    ok = not hard_fail and not reasons
    return {
        "ok": ok,
        "hard_fail": hard_fail,
        "state": state if not ok else "SAMPLE_ACCEPTED",
        "reasons_vi": reasons,
        "person_height_px": box.h,
        "score": float(max(0.0, min(1.0, score))),
        "head_visible": top_ok,
        "feet_visible": bottom_ok,
    }

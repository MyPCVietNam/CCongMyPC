"""Face quality evaluation — synthetic-friendly heuristics."""

from __future__ import annotations

import math

from app.vision.faces.types import FaceBox, QualityReport


def evaluate_face_quality(
    image_w: int,
    image_h: int,
    box: FaceBox,
    *,
    min_face_px: int = 40,
    max_faces_ok: int = 1,
    face_count: int = 1,
    blur_score: float = 1.0,
) -> QualityReport:
    reasons: list[str] = []
    if face_count == 0:
        return QualityReport(
            ok=False,
            score=0.0,
            face_width_px=0,
            blur_score=blur_score,
            reasons_vi=["Không tìm thấy khuôn mặt phù hợp. Hãy thử lại hoặc dùng phương án chấm công thay thế."],
        )
    if face_count > max_faces_ok:
        return QualityReport(
            ok=False,
            score=0.0,
            face_width_px=box.w,
            blur_score=blur_score,
            reasons_vi=["Phát hiện nhiều khuôn mặt. Chỉ một nhân viên được phép trong khung đăng ký."],
        )
    if box.w < min_face_px or box.h < min_face_px:
        reasons.append(
            f"Ảnh khuôn mặt không đủ rõ ({box.w}×{box.h} px). Vui lòng đứng gần và nhìn lên camera."
        )
    # Edge crop check
    margin = 2
    if box.x < margin or box.y < margin or box.x + box.w > image_w - margin or box.y + box.h > image_h - margin:
        reasons.append("Khuôn mặt bị cắt mép khung hình.")
    if blur_score < 0.25:
        reasons.append("Ảnh bị mờ. Giữ yên và nhìn thẳng vào camera.")
    # Relative size score
    rel = box.w / max(image_w, 1)
    size_score = min(1.0, rel / 0.15)
    score = max(0.0, min(1.0, 0.5 * size_score + 0.5 * blur_score))
    if math.isnan(score) or math.isinf(score):
        reasons.append("Điểm chất lượng không hợp lệ.")
        score = 0.0
    ok = not reasons and score >= 0.35
    if not ok and not reasons:
        reasons.append("Chất lượng khuôn mặt chưa đạt. Vui lòng chụp lại.")
    return QualityReport(
        ok=ok,
        score=score,
        face_width_px=box.w,
        blur_score=blur_score,
        reasons_vi=reasons,
        metadata={"image_w": image_w, "image_h": image_h, "rel_width": rel},
    )

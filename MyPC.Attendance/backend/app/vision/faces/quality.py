"""Face quality evaluation with hard gates (P01.5)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.vision.faces.types import FaceBox, PoseEstimate, QualityReport

# Starting experimental targets (calibrate on EZVIZ lab)
MIN_FACE_WIDTH_PX = 120
PREFERRED_FACE_WIDTH_PX = 160
MIN_INTER_EYE_PX = 40
MIN_LAPLACIAN_VAR = 40.0
MIN_DETECTION_SCORE = 0.6


def estimate_pose_from_landmarks(box: FaceBox) -> PoseEstimate:
    """
    Rough yaw/pitch/roll from 5 YuNet landmarks.
    Landmarks order: right_eye, left_eye, nose, right_mouth, left_mouth (image coords).
    Instructions use EMPLOYEE perspective: FACE_LEFT = employee turns head to their left.
    """
    if len(box.landmarks) < 3:
        return PoseEstimate(0.0, 0.0, 0.0, "UNKNOWN", 0.0)
    re, le, nose = box.landmarks[0], box.landmarks[1], box.landmarks[2]
    eye_mid_x = (re[0] + le[0]) / 2.0
    eye_mid_y = (re[1] + le[1]) / 2.0
    inter_eye = float(np.hypot(le[0] - re[0], le[1] - re[1])) or 1.0
    # Nose offset from eye midpoint normalized by inter-eye → yaw proxy
    # Positive yaw_deg ≈ face rotated so nose shifts toward image-left
    # (employee turned their head to their RIGHT from their perspective if camera is front-facing).
    nose_dx = (nose[0] - eye_mid_x) / inter_eye
    nose_dy = (nose[1] - eye_mid_y) / inter_eye
    yaw = float(np.clip(-nose_dx * 45.0, -60.0, 60.0))  # employee-left ≈ positive yaw
    pitch = float(np.clip((nose_dy - 0.35) * 40.0, -40.0, 40.0))
    roll = float(np.degrees(math.atan2(le[1] - re[1], le[0] - re[0])))
    conf = 0.55 if inter_eye >= MIN_INTER_EYE_PX else 0.25
    # Slot from employee perspective: FACE_LEFT = turn head left ≈ nose toward image-right ≈ yaw > 0
    if abs(yaw) < 12 and abs(pitch) < 18:
        slot = "FACE_FRONT"
    elif yaw >= 15:
        slot = "FACE_LEFT"
    elif yaw <= -15:
        slot = "FACE_RIGHT"
    else:
        slot = "UNKNOWN"
    return PoseEstimate(yaw, pitch, roll, slot, conf)


def _laplacian_variance(gray: np.ndarray) -> float:
    try:
        import cv2  # type: ignore

        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return float(np.std(gray))


def _illumination_stats(gray: np.ndarray) -> dict[str, float]:
    mean = float(np.mean(gray))
    std = float(np.std(gray))
    p05 = float(np.percentile(gray, 5))
    p95 = float(np.percentile(gray, 95))
    # Asymmetric shadow: left vs right half mean difference
    mid = gray.shape[1] // 2
    left_m = float(np.mean(gray[:, :mid])) if mid > 0 else mean
    right_m = float(np.mean(gray[:, mid:])) if mid > 0 else mean
    return {
        "mean": mean,
        "std": std,
        "p05": p05,
        "p95": p95,
        "asymmetry": abs(left_m - right_m),
    }


def evaluate_face_quality(
    image: np.ndarray | None,
    image_w: int,
    image_h: int,
    box: FaceBox,
    *,
    min_face_px: int = MIN_FACE_WIDTH_PX,
    max_faces_ok: int = 1,
    face_count: int = 1,
    blur_score: float | None = None,
    expected_slot: str | None = None,
) -> QualityReport:
    reasons: list[str] = []
    hard_fail = False
    breakdown: dict[str, Any] = {}
    pose = estimate_pose_from_landmarks(box) if box.w > 0 else None
    inter_eye = box.inter_eye_px
    laplacian_var = 0.0
    illum: dict[str, float] = {}

    if face_count == 0:
        return QualityReport(
            ok=False,
            score=0.0,
            face_width_px=0,
            inter_eye_px=0.0,
            blur_score=0.0,
            laplacian_var=0.0,
            pose=None,
            hard_fail=True,
            reasons_vi=[
                "Không tìm thấy khuôn mặt phù hợp. Hãy đứng vào khung hình và nhìn về phía camera."
            ],
            breakdown={"state": "WAITING_FOR_PERSON"},
            metadata={"image_w": image_w, "image_h": image_h},
        )
    if face_count > max_faces_ok:
        return QualityReport(
            ok=False,
            score=0.0,
            face_width_px=box.w,
            inter_eye_px=inter_eye,
            blur_score=0.0,
            laplacian_var=0.0,
            pose=pose,
            hard_fail=True,
            reasons_vi=[
                "Phát hiện nhiều người/khuôn mặt. Chỉ giữ đúng một nhân viên trong khung hình đăng ký."
            ],
            breakdown={"state": "MULTIPLE_PEOPLE"},
            metadata={"image_w": image_w, "image_h": image_h, "face_count": face_count},
        )

    # Crop for sharpness / illumination
    if image is not None and image.size and box.w > 0 and box.h > 0:
        x2, y2 = min(image_w, box.x + box.w), min(image_h, box.y + box.h)
        crop = image[max(0, box.y) : y2, max(0, box.x) : x2]
        if crop.size:
            if crop.ndim == 3:
                gray = np.mean(crop, axis=2).astype(np.uint8)
            else:
                gray = crop.astype(np.uint8)
            laplacian_var = _laplacian_variance(gray)
            illum = _illumination_stats(gray)

    if blur_score is None:
        # Normalize Laplacian roughly to 0..1 for scoring (soft)
        blur_score = float(np.clip(laplacian_var / 200.0, 0.0, 1.0))

    if box.score < MIN_DETECTION_SCORE:
        hard_fail = True
        reasons.append("Độ tin cậy phát hiện khuôn mặt thấp.")

    if box.w < min_face_px or box.h < min_face_px:
        hard_fail = True
        reasons.append(
            f"Khuôn mặt quá nhỏ ({box.w}×{box.h} px, cần ≥{min_face_px} px). Hãy đứng gần camera hơn."
        )
        breakdown["state"] = "TOO_FAR"

    if inter_eye > 0 and inter_eye < MIN_INTER_EYE_PX:
        hard_fail = True
        reasons.append(
            f"Khoảng cách hai mắt quá nhỏ ({inter_eye:.0f} px, cần ≥{MIN_INTER_EYE_PX} px)."
        )
        breakdown["state"] = "TOO_FAR"

    margin = max(4, int(0.02 * min(image_w, image_h)))
    if (
        box.x < margin
        or box.y < margin
        or box.x + box.w > image_w - margin
        or box.y + box.h > image_h - margin
    ):
        hard_fail = True
        reasons.append("Khuôn mặt bị cắt mép khung hình.")

    if laplacian_var < MIN_LAPLACIAN_VAR:
        hard_fail = True
        reasons.append("Ảnh bị mờ (độ nét Laplacian thấp). Giữ yên và nhìn rõ vào camera.")
        breakdown["state"] = "BLURRY"

    if illum:
        if illum["mean"] < 40 or illum["p95"] < 60:
            hard_fail = True
            reasons.append("Ảnh quá tối. Hãy cải thiện ánh sáng.")
            breakdown["state"] = "TOO_DARK"
        elif illum["mean"] > 220 or illum["p05"] > 200:
            hard_fail = True
            reasons.append("Ảnh bị cháy sáng / quá sáng.")
            breakdown["state"] = "TOO_DARK"  # reuse guidance bucket; UI maps exposure
        if illum["asymmetry"] > 55 and illum["std"] < 35:
            reasons.append("Bóng đổ lệch mạnh trên khuôn mặt — điều chỉnh ánh sáng.")

    if pose and expected_slot and pose.slot_hint not in {expected_slot, "UNKNOWN"}:
        # Soft mismatch — do not hard-fail solely on uncertain pose
        if pose.confidence >= 0.5 and pose.slot_hint != expected_slot:
            reasons.append(
                f"Góc mặt chưa khớp yêu cầu ({expected_slot}). Hiện ước lượng: {pose.slot_hint}."
            )

    # Soft size preference
    size_score = min(1.0, box.w / float(PREFERRED_FACE_WIDTH_PX))
    sharpness_score = float(np.clip(laplacian_var / 200.0, 0.0, 1.0))
    illum_score = 1.0
    if illum:
        # Prefer mid-range mean ~110
        illum_score = float(np.clip(1.0 - abs(illum["mean"] - 110) / 110.0, 0.0, 1.0))
    det_score = float(np.clip(box.score, 0.0, 1.0))
    score = max(
        0.0,
        min(1.0, 0.35 * size_score + 0.35 * sharpness_score + 0.15 * illum_score + 0.15 * det_score),
    )
    if math.isnan(score) or math.isinf(score):
        hard_fail = True
        reasons.append("Điểm chất lượng không hợp lệ.")
        score = 0.0

    # Hard failure always overrides weighted average
    ok = (not hard_fail) and (not reasons) and score >= 0.40
    if hard_fail:
        ok = False
    if not ok and not reasons:
        reasons.append("Chất lượng khuôn mặt chưa đạt. Vui lòng chụp lại.")

    breakdown.update(
        {
            "size_score": size_score,
            "sharpness_score": sharpness_score,
            "illum_score": illum_score,
            "detection_score": det_score,
            "illumination": illum,
            "min_face_px": min_face_px,
            "preferred_face_px": PREFERRED_FACE_WIDTH_PX,
        }
    )
    return QualityReport(
        ok=ok,
        score=score,
        face_width_px=box.w,
        inter_eye_px=inter_eye,
        blur_score=float(blur_score),
        laplacian_var=laplacian_var,
        pose=pose,
        hard_fail=hard_fail,
        reasons_vi=reasons,
        breakdown=breakdown,
        metadata={
            "image_w": image_w,
            "image_h": image_h,
            "rel_width": box.w / max(image_w, 1),
            "detection_score": box.score,
        },
    )

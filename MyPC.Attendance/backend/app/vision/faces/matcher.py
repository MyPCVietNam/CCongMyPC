"""Face matcher — never force nearest-neighbor assignment."""

from __future__ import annotations

import numpy as np

from app.vision.faces.types import MatchOutcome, VerificationResult


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def match_embedding(
    probe: np.ndarray,
    gallery: list[tuple[int, np.ndarray]],
    *,
    threshold: float = 0.45,
    margin: float = 0.05,
    model_id: str = "",
) -> VerificationResult:
    """
    gallery: list of (employee_id, embedding)
    Ambiguous when top1-top2 < margin even if top1 >= threshold.
    """
    if not gallery:
        return VerificationResult(
            outcome=MatchOutcome.UNKNOWN,
            employee_id=None,
            similarity=0.0,
            second_best_similarity=0.0,
            message_vi="Không có mẫu khuôn mặt đã đăng ký.",
            model_id=model_id,
            threshold=threshold,
        )

    scored: list[tuple[float, int]] = []
    for emp_id, vec in gallery:
        scored.append((cosine_similarity(probe, vec), emp_id))
    scored.sort(key=lambda x: (-x[0], x[1]))
    best_sim, best_id = scored[0]
    second = scored[1][0] if len(scored) > 1 else -1.0

    if best_sim < threshold:
        return VerificationResult(
            outcome=MatchOutcome.UNKNOWN,
            employee_id=None,
            similarity=best_sim,
            second_best_similarity=second,
            message_vi="Không tìm thấy khuôn mặt phù hợp. Hãy thử lại hoặc dùng phương án chấm công thay thế.",
            model_id=model_id,
            threshold=threshold,
        )

    if second >= 0 and (best_sim - second) < margin:
        return VerificationResult(
            outcome=MatchOutcome.AMBIGUOUS,
            employee_id=None,
            similarity=best_sim,
            second_best_similarity=second,
            message_vi="Không xác định được danh tính (điểm gần nhau). Cần đối soát thủ công.",
            model_id=model_id,
            threshold=threshold,
        )

    return VerificationResult(
        outcome=MatchOutcome.MATCH,
        employee_id=best_id,
        similarity=best_sim,
        second_best_similarity=second,
        message_vi="Đã xác minh danh tính nhân viên.",
        model_id=model_id,
        threshold=threshold,
    )

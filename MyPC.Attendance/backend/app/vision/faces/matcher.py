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
    gallery: list of (employee_id, embedding) — multiple templates per employee allowed.
    Scores are aggregated best-by-identity; margin is applied between top-two identities
    (not between two templates of the same person).
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

    best_by_emp: dict[int, float] = {}
    for emp_id, vec in gallery:
        sim = cosine_similarity(probe, vec)
        if emp_id not in best_by_emp or sim > best_by_emp[emp_id]:
            best_by_emp[emp_id] = sim

    ranked = sorted(best_by_emp.items(), key=lambda x: (-x[1], x[0]))
    best_id, best_sim = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else -1.0

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

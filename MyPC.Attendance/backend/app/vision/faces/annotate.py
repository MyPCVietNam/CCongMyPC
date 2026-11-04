"""Draw detection boxes + ROI on a cloned BGR frame (never mutates source)."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from app.vision.faces.types import FaceBox


def annotate_detection_bgr(
    bgr: np.ndarray,
    faces: Sequence[FaceBox | dict[str, Any]],
    *,
    roi_norm: dict[str, float] | None = None,
    status_label: str = "",
    primary_index: int | None = None,
) -> np.ndarray:
    """Return a new annotated BGR image. Source ``bgr`` is never modified in place."""
    import cv2

    out = np.ascontiguousarray(bgr).copy()
    h, w = out.shape[:2]
    if roi_norm:
        x = int(float(roi_norm.get("x", 0)) * w)
        y = int(float(roi_norm.get("y", 0)) * h)
        rw = int(float(roi_norm.get("w", 0)) * w)
        rh = int(float(roi_norm.get("h", 0)) * h)
        cv2.rectangle(out, (x, y), (x + max(rw, 1), y + max(rh, 1)), (80, 200, 255), 2)

    for i, face in enumerate(faces):
        if isinstance(face, FaceBox):
            fx, fy, fw, fh = int(face.x), int(face.y), int(face.w), int(face.h)
            score = float(face.score)
        else:
            fx = int(face.get("x_px", face.get("x", 0)))
            fy = int(face.get("y_px", face.get("y", 0)))
            fw = int(face.get("w_px", face.get("w", 0)))
            fh = int(face.get("h_px", face.get("h", 0)))
            score = float(face.get("score", 0.0))
        color = (40, 220, 40) if primary_index is None or i == primary_index else (40, 180, 255)
        cv2.rectangle(out, (fx, fy), (fx + max(fw, 1), fy + max(fh, 1)), color, 2)
        label = f"{score:.2f} {fw}px"
        cv2.putText(
            out,
            label,
            (fx, max(fy - 6, 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA,
        )

    if status_label:
        cv2.putText(
            out,
            status_label[:64],
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (30, 30, 240) if status_label not in {"OK", "FACE_OK"} else (40, 220, 40),
            2,
            cv2.LINE_AA,
        )
    return out

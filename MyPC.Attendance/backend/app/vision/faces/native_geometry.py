"""Inverse-map YuNet detection rows from tensor space to native pixel coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Transform:
    native_width: int
    native_height: int
    tensor_width: int
    tensor_height: int
    scale_x: float
    scale_y: float
    pad_x: float = 0.0
    pad_y: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.native_width, self.native_height, self.tensor_width, self.tensor_height):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError("dimensions must be positive integers")
        if any(not math.isfinite(v) for v in (self.scale_x, self.scale_y, self.pad_x, self.pad_y)):
            raise ValueError("non-finite scale/padding")
        if self.scale_x <= 0 or self.scale_y <= 0:
            raise ValueError("scales must be positive")


def resize_transform(native_width: int, native_height: int, tensor_width: int, tensor_height: int) -> Transform:
    return Transform(
        native_width,
        native_height,
        tensor_width,
        tensor_height,
        tensor_width / native_width,
        tensor_height / native_height,
    )


def letterbox_transform(
    native_width: int, native_height: int, tensor_width: int, tensor_height: int
) -> Transform:
    nominal = min(tensor_width / native_width, tensor_height / native_height)
    scaled_w = min(tensor_width, max(1, round(native_width * nominal)))
    scaled_h = min(tensor_height, max(1, round(native_height * nominal)))
    left = (tensor_width - scaled_w) // 2
    top = (tensor_height - scaled_h) // 2
    return Transform(
        native_width,
        native_height,
        tensor_width,
        tensor_height,
        scaled_w / native_width,
        scaled_h / native_height,
        float(left),
        float(top),
    )


def inverse_point(x: float, y: float, t: Transform) -> tuple[float, float]:
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("non-finite input coordinates")
    return ((x - t.pad_x) / t.scale_x, (y - t.pad_y) / t.scale_y)


def map_yunet_row_to_native(
    row: Sequence[float], t: Transform, *, tolerance: float = 0.001
) -> tuple[float, ...]:
    if len(row) != 15:
        raise ValueError("YuNet detection row must have exactly 15 elements")
    v = [float(x) for x in row]
    if any(not math.isfinite(x) for x in v):
        raise ValueError("non-finite YuNet coordinates")
    if v[2] <= 0 or v[3] <= 0 or not (0.0 <= v[14] <= 1.0):
        raise ValueError("invalid bbox size/confidence")
    x0, y0 = inverse_point(v[0], v[1], t)
    x1, y1 = inverse_point(v[0] + v[2], v[1] + v[3], t)
    points = [inverse_point(v[i], v[i + 1], t) for i in range(4, 14, 2)]
    corners = [(x0, y0), (x1, y1), *points]
    if any(
        x < -tolerance or y < -tolerance or x > t.native_width + tolerance or y > t.native_height + tolerance
        for x, y in corners
    ):
        raise ValueError("geometry exceeds native image bounds")
    out = [x0, y0, x1 - x0, y1 - y0]
    for point in points:
        out.extend(point)
    out.append(v[14])
    return tuple(out)


def native_face_quality_gate(
    row_native: Sequence[float],
    *,
    min_face_width: float = 120.0,
    min_inter_eye: float = 40.0,
) -> dict[str, float | bool]:
    """Provisional on-site thresholds — not a universal accuracy claim."""
    if len(row_native) != 15:
        raise ValueError("expected 15-element native YuNet row")
    width = float(row_native[2])
    distance = math.hypot(row_native[4] - row_native[6], row_native[5] - row_native[7])
    return {
        "face_width_native_px": round(width, 4),
        "inter_eye_native_px": round(distance, 4),
        "provisional_pass": width >= min_face_width and distance >= min_inter_eye,
        "note": "Upscaling never satisfies the hard native pixel gate.",
    }

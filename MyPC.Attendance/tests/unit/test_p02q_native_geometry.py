"""P02Q native YuNet inverse map — UNIT_SYNTHETIC."""

from __future__ import annotations

import pytest

from app.vision.faces.native_geometry import (
    letterbox_transform,
    map_yunet_row_to_native,
    native_face_quality_gate,
    resize_transform,
)


def _sample_row(t, *, native_bbox=(600, 300, 240, 240)):
    x, y, w, h = native_bbox
    points = [
        (x + 50, y + 70),
        (x + 180, y + 70),
        (x + 120, y + 125),
        (x + 70, y + 195),
        (x + 165, y + 195),
    ]
    row = [x * t.scale_x + t.pad_x, y * t.scale_y + t.pad_y, w * t.scale_x, h * t.scale_y]
    for a, b in points:
        row.extend([a * t.scale_x + t.pad_x, b * t.scale_y + t.pad_y])
    row.append(0.91)
    return row


def test_2880_resize_five_landmarks():
    t = resize_transform(2880, 1620, 960, 540)
    row = map_yunet_row_to_native(_sample_row(t), t)
    assert row[0] == pytest.approx(600)
    assert row[2] == pytest.approx(240)
    assert row[4] == pytest.approx(650)
    assert row[-1] == 0.91
    assert native_face_quality_gate(row)["provisional_pass"] is True


def test_letterbox_padding():
    t = letterbox_transform(2880, 1620, 640, 640)
    assert t.pad_y == 140
    row = map_yunet_row_to_native(_sample_row(t), t)
    assert row[0] == pytest.approx(600)
    assert row[12] == pytest.approx(765)


def test_anisotropic_resize():
    t = resize_transform(1280, 720, 320, 240)
    row = map_yunet_row_to_native(_sample_row(t, native_bbox=(100, 100, 200, 150)), t)
    assert row[2] == pytest.approx(200)
    assert row[3] == pytest.approx(150)


def test_reject_nan_and_oob():
    t = letterbox_transform(2880, 1620, 640, 640)
    row = _sample_row(t)
    row[4] = -100
    with pytest.raises(ValueError):
        map_yunet_row_to_native(row, t)
    t2 = resize_transform(2880, 1620, 960, 540)
    row2 = _sample_row(t2)
    row2[5] = float("nan")
    with pytest.raises(ValueError):
        map_yunet_row_to_native(row2, t2)


def test_upscale_does_not_pass_native_gate():
    t = resize_transform(2880, 1620, 960, 540)
    row = map_yunet_row_to_native(_sample_row(t, native_bbox=(600, 300, 80, 90)), t)
    gate = native_face_quality_gate(row)
    assert gate["provisional_pass"] is False
    assert gate["face_width_native_px"] < 120

"""P02 unit: shared LIVE face-detect preview service (synthetic frames only)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from app.services.live_face_detect_preview import LiveFaceDetectPreviewService
from app.vision.camera.gateway import CameraFrame, ClockTrust, DecoderStatus, StreamProvenance
from app.vision.faces.annotate import annotate_detection_bgr
from app.vision.faces.types import FaceBox, InferenceMode, PoseEstimate, QualityReport


def _frame(
    *,
    frame_id: str = "f1",
    provenance: StreamProvenance = StreamProvenance.CAMERA_LIVE,
    status: DecoderStatus = DecoderStatus.OK,
    w: int = 320,
    h: int = 240,
) -> CameraFrame:
    img = np.full((h, w, 3), 40, dtype=np.uint8)
    now = datetime.now(timezone.utc)
    return CameraFrame.from_bgr(
        img,
        frame_id=frame_id,
        camera_id="1",
        capture_time_utc=now,
        receive_time_utc=now,
        provenance=provenance,
        decoder_status=status,
        config_revision="rev-a",
        clock_trust=ClockTrust.SERVER_RECEIVE,
        integrity_ok=True,
    )


class _FakePipeline:
    def __init__(self, faces: list[FaceBox], quality: QualityReport, mode=InferenceMode.REAL, ready=True):
        self._faces = faces
        self._quality = quality
        self.inference_mode = mode
        self.detector = SimpleNamespace(info=SimpleNamespace(ready=ready, backend="opencv_dnn"))

    def detect_and_quality(self, image, *, expected_slot=None, max_faces_ok=1):
        assert image.flags["OWNDATA"] or True
        return list(self._faces), self._quality


def _q(**kwargs):
    base = dict(
        ok=True,
        score=0.9,
        face_width_px=160,
        inter_eye_px=50.0,
        blur_score=1.0,
        laplacian_var=100.0,
        pose=PoseEstimate(0, 0, 0, "FACE_FRONT", 0.8),
        hard_fail=False,
        reasons_vi=[],
        breakdown={},
        metadata={},
    )
    base.update(kwargs)
    return QualityReport(**base)


def test_annotate_does_not_mutate_source():
    src = np.zeros((100, 120, 3), dtype=np.uint8)
    before = src.copy()
    out = annotate_detection_bgr(src, [FaceBox(10, 10, 40, 50, score=0.9)], roi_norm={"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5})
    assert np.array_equal(src, before)
    assert out is not src
    assert out.shape == src.shape


def test_reject_mock_and_stale_and_not_ready():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.01, max_interval_s=0.05)
    mock_fr = _frame(provenance=StreamProvenance.MOCK)
    snap, _ = svc.analyze_frame(
        camera_id=1,
        frame=mock_fr,
        face_pipeline=_FakePipeline([], _q(ok=False), mode=InferenceMode.REAL),
        roi_norm=None,
        force=True,
    )
    assert snap.status == "REJECTED_MOCK"
    assert snap.faces == []

    stale = _frame(status=DecoderStatus.STALE, frame_id="stale")
    snap2, _ = svc.analyze_frame(
        camera_id=1,
        frame=stale,
        face_pipeline=_FakePipeline([], _q(ok=False)),
        roi_norm=None,
        force=True,
    )
    assert snap2.status == "STALE_FRAME"

    synth = _FakePipeline([], _q(ok=False), mode=InferenceMode.SYNTHETIC_FIXTURE, ready=True)
    snap3, _ = svc.analyze_frame(
        camera_id=1,
        frame=_frame(frame_id="syn"),
        face_pipeline=synth,
        roi_norm=None,
        force=True,
    )
    assert snap3.status == "NOT_READY"
    assert snap3.faces == []


def test_no_face_one_face_too_small_multiple():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.01, max_interval_s=0.05)
    roi = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}

    snap, _ = svc.analyze_frame(
        camera_id=2,
        frame=_frame(frame_id="nf"),
        face_pipeline=_FakePipeline([], _q(ok=False, face_width_px=0, hard_fail=True, reasons_vi=["no"])),
        roi_norm=roi,
        force=True,
    )
    assert snap.status == "NO_FACE"
    assert snap.enrollment_gate == "NO_FACE"

    ok_face = FaceBox(40, 40, 160, 180, score=0.92)
    snap_ok, ann = svc.analyze_frame(
        camera_id=2,
        frame=_frame(frame_id="ok"),
        face_pipeline=_FakePipeline([ok_face], _q()),
        roi_norm=roi,
        force=True,
        want_annotated=True,
    )
    assert snap_ok.status == "OK"
    assert snap_ok.face_count == 1
    assert snap_ok.faces[0]["w_px"] == 160
    assert snap_ok.identity_exposed is False
    assert snap_ok.attendance_written is False
    assert ann is not None and ann.shape[0] == 240

    small = FaceBox(10, 10, 80, 90, score=0.7)
    snap_s, _ = svc.analyze_frame(
        camera_id=2,
        frame=_frame(frame_id="sm"),
        face_pipeline=_FakePipeline(
            [small],
            _q(ok=False, face_width_px=80, hard_fail=True, breakdown={"state": "TOO_SMALL"}, reasons_vi=["small"]),
        ),
        roi_norm=roi,
        force=True,
    )
    assert snap_s.status == "FACE_TOO_SMALL"

    multi = [FaceBox(10, 10, 130, 140, 0.9), FaceBox(180, 20, 130, 140, 0.88)]
    snap_m, _ = svc.analyze_frame(
        camera_id=2,
        frame=_frame(frame_id="mu"),
        face_pipeline=_FakePipeline(
            multi,
            _q(ok=False, face_width_px=130, hard_fail=True, reasons_vi=["multi"]),
        ),
        roi_norm=roi,
        force=True,
    )
    assert snap_m.status == "MULTIPLE_FACES"
    assert snap_m.enrollment_gate == "MULTIPLE_FACES"
    assert snap_m.face_count == 2


def test_outside_roi_and_cache_same_frame():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    face = FaceBox(10, 10, 160, 180, score=0.9)
    pipe = _FakePipeline([face], _q())
    roi = {"x": 0.8, "y": 0.8, "w": 0.15, "h": 0.15}
    fr = _frame(frame_id="same")
    a, _ = svc.analyze_frame(camera_id=3, frame=fr, face_pipeline=pipe, roi_norm=roi, force=True)
    assert a.status == "OUTSIDE_ROI"
    b, _ = svc.analyze_frame(camera_id=3, frame=fr, face_pipeline=pipe, roi_norm=roi, force=False)
    assert b.cache_hit is True
    assert b.frame_id == "same"


def test_frame_id_matches_snapshot():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.01, max_interval_s=0.05)
    fr = _frame(frame_id="unique-xyz")
    snap, _ = svc.analyze_frame(
        camera_id=9,
        frame=fr,
        face_pipeline=_FakePipeline([FaceBox(20, 20, 160, 170, 0.9)], _q()),
        roi_norm={"x": 0, "y": 0, "w": 1, "h": 1},
        force=True,
    )
    assert snap.frame_id == "unique-xyz"
    assert snap.config_revision == "rev-a"

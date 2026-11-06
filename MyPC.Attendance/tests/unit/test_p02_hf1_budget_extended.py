"""P02-HF1 extended regressions — synthetic frames only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Thread
from types import SimpleNamespace

import numpy as np

from app.services.live_face_detect_preview import LiveFaceDetectPreviewService
from app.vision.camera.gateway import CameraFrame, ClockTrust, DecoderStatus, StreamProvenance
from app.vision.faces.types import FaceBox, InferenceMode, QualityReport

_ROI = dict(x=0.0, y=0.0, w=1.0, h=1.0)


def _frame(fid: str, *, rev: str = "rev-a") -> CameraFrame:
    now = datetime.now(timezone.utc)
    return CameraFrame.from_bgr(
        np.full((240, 320, 3), 42, dtype=np.uint8),
        frame_id=fid,
        camera_id="1",
        capture_time_utc=now,
        receive_time_utc=now,
        provenance=StreamProvenance.CAMERA_LIVE,
        decoder_status=DecoderStatus.OK,
        config_revision=rev,
        clock_trust=ClockTrust.SERVER_RECEIVE,
        integrity_ok=True,
    )


class CountingDetector:
    def __init__(self, block_on_call: int | None = None):
        self.detector = SimpleNamespace(info=SimpleNamespace(ready=True, backend="opencv_dnn"))
        self.inference_mode = InferenceMode.REAL
        self.calls = 0
        self.entered = Event()
        self.release = Event()
        self.block_on_call = block_on_call

    def detect_and_quality(self, image, *, expected_slot=None, max_faces_ok=1):
        self.calls += 1
        if self.calls == self.block_on_call:
            self.entered.set()
            assert self.release.wait(timeout=5)
        face = FaceBox(20, 20, 140, 145, score=0.98)
        q = QualityReport(
            ok=True,
            score=0.95,
            face_width_px=140,
            inter_eye_px=36.0,
            blur_score=1.0,
            laplacian_var=150.0,
            pose=None,
            hard_fail=False,
            reasons_vi=[],
            breakdown={},
            metadata={},
        )
        return [face], q


def test_f1_f2_f3_budget_and_throttle_status():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector()
    s1, _ = svc.analyze_frame(
        camera_id=1, frame=_frame("f1"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0
    )
    s2, _ = svc.analyze_frame(
        camera_id=1, frame=_frame("f2"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0
    )
    s3, _ = svc.analyze_frame(
        camera_id=1, frame=_frame("f3"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=3.0
    )
    assert pipe.calls == 1
    assert s1.analyzed and s1.frame_id == "f1"
    assert s2.frame_id == "f2" and s2.status == "AI_THROTTLED" and s2.faces == []
    assert s3.frame_id == "f3" and s3.status == "AI_THROTTLED"
    assert s2.enrollment_gate != "NO_FACE"
    assert s2.identity_exposed is False and s2.attendance_written is False


def test_client_cannot_raise_server_budget():
    svc = LiveFaceDetectPreviewService(
        min_interval_s=0.5, max_interval_s=1.0, server_ai_fps_cap=2.0
    )
    # Even if client asks for 3 FPS, interval stays >= 0.5
    assert svc._interval(3.0) >= 0.5
    assert svc._interval(1.0) >= 0.5


def test_same_frame_cache_hit_no_extra_infer():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector()
    fr = _frame("same")
    a, _ = svc.analyze_frame(
        camera_id=1, frame=fr, face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0, want_annotated=True
    )
    b, _ = svc.analyze_frame(
        camera_id=1, frame=fr, face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0, want_annotated=True
    )
    assert pipe.calls == 1
    assert a.analyzed and b.cache_hit and b.frame_id == "same"


def test_inflight_returns_ai_busy_for_current_frame():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.01, max_interval_s=0.05)
    pipe = CountingDetector(block_on_call=1)
    errors = []

    def bg():
        try:
            svc.analyze_frame(
                camera_id=7,
                frame=_frame("slow"),
                face_pipeline=pipe,
                roi_norm=_ROI,
                max_ai_fps=2.0,
                want_annotated=True,
            )
        except Exception as exc:
            errors.append(exc)

    t = Thread(target=bg)
    t.start()
    assert pipe.entered.wait(timeout=3)
    snap, ann = svc.analyze_frame(
        camera_id=7,
        frame=_frame("other"),
        face_pipeline=pipe,
        roi_norm=_ROI,
        max_ai_fps=2.0,
        want_annotated=True,
    )
    assert snap.frame_id == "other"
    assert snap.status == "AI_BUSY"
    assert snap.faces == []
    if ann is not None:
        assert snap.frame_id == "other"
    pipe.release.set()
    t.join(timeout=4)
    assert not errors


def test_two_concurrent_clients_do_not_multiply_inference():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector()
    # Prime one analysis
    svc.analyze_frame(
        camera_id=3, frame=_frame("c0"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0
    )
    baseline = pipe.calls

    def client(i: int):
        return svc.analyze_frame(
            camera_id=3,
            frame=_frame(f"c{i}"),
            face_pipeline=pipe,
            roi_norm=_ROI,
            max_ai_fps=2.0,
            want_annotated=True,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(client, range(1, 5)))
    # Within budget window, additional clients must not multiply YuNet calls
    assert pipe.calls == baseline


def test_clear_camera_invalidates_cache_and_generation():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector()
    svc.analyze_frame(
        camera_id=4, frame=_frame("x1"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0
    )
    svc.clear_camera(4)
    # After clear, new analysis allowed immediately
    svc.analyze_frame(
        camera_id=4, frame=_frame("x2"), face_pipeline=pipe, roi_norm=_ROI, max_ai_fps=2.0
    )
    assert pipe.calls == 2


def test_revision_change_does_not_reuse_boxes_as_new_frame():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.01, max_interval_s=0.05)
    pipe = CountingDetector()
    s1, _ = svc.analyze_frame(
        camera_id=5,
        frame=_frame("r1", rev="rev-1"),
        face_pipeline=pipe,
        roi_norm=_ROI,
        max_ai_fps=2.0,
        force=True,
    )
    assert s1.frame_id == "r1"
    s2, _ = svc.analyze_frame(
        camera_id=5,
        frame=_frame("r2", rev="rev-2"),
        face_pipeline=pipe,
        roi_norm=_ROI,
        max_ai_fps=2.0,
        force=True,
    )
    assert s2.frame_id == "r2"
    assert s2.config_revision == "rev-2"

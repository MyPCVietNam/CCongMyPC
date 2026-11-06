"""Independent P02-HF1 RED regressions for Cursor; synthetic frames only.

Run at repository root:
  PYTHONPATH=backend python -m pytest -q repro/test_p02_hf1_frame_cache_regressions.py
No real camera, secrets, face images or DataDir involved.

Assertions are preserved exactly from the independent audit handoff. The overlapping
race uses ``force=True`` only as fixture plumbing so f2 can enter the detector under
the corrected global budget (without force, f2 would be AI_THROTTLED and never
block — which is correct production behavior, but would skip the race assertion).
"""
from datetime import datetime, timezone
from threading import Event, Thread
from types import SimpleNamespace

import numpy as np

from app.services.live_face_detect_preview import LiveFaceDetectPreviewService
from app.vision.camera.gateway import CameraFrame, ClockTrust, DecoderStatus, StreamProvenance
from app.vision.faces.types import FaceBox, InferenceMode, QualityReport


def _frame(fid: str) -> CameraFrame:
    now = datetime.now(timezone.utc)
    return CameraFrame.from_bgr(
        np.full((240, 320, 3), 42, dtype=np.uint8),
        frame_id=fid, camera_id="1", capture_time_utc=now,
        receive_time_utc=now, provenance=StreamProvenance.CAMERA_LIVE,
        decoder_status=DecoderStatus.OK, config_revision="rev-synthetic",
        clock_trust=ClockTrust.SERVER_RECEIVE, integrity_ok=True,
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
            if not self.release.wait(timeout=5):
                raise AssertionError("Synthetic inference release timed out")
        face = FaceBox(20, 20, 140, 145, score=0.98)
        q = QualityReport(
            ok=True, score=0.95, face_width_px=140, inter_eye_px=36.0,
            blur_score=1.0, laplacian_var=150.0, pose=None, hard_fail=False,
            reasons_vi=[], breakdown={}, metadata={},
        )
        return [face], q


_ROI = dict(x=0.0, y=0.0, w=1.0, h=1.0)


def test_global_inference_budget_applies_across_distinct_frame_ids():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector()
    svc.analyze_frame(camera_id=1, frame=_frame("f1"), face_pipeline=pipe, roi_norm=_ROI,
                      max_ai_fps=2.0, want_annotated=True)
    svc.analyze_frame(camera_id=1, frame=_frame("f2"), face_pipeline=pipe, roi_norm=_ROI,
                      max_ai_fps=2.0, want_annotated=True)
    assert pipe.calls <= 1, (
        f"P02 budget bypass: {pipe.calls} inferences in <0.5s on distinct frames; "
        "a shared per-camera 2 FPS budget must not be keyed only by frame_id"
    )


def test_overlapping_requests_never_return_old_frame_as_current():
    svc = LiveFaceDetectPreviewService(min_interval_s=0.5, max_interval_s=1.0)
    pipe = CountingDetector(block_on_call=2)
    svc.analyze_frame(camera_id=1, frame=_frame("f1"), face_pipeline=pipe, roi_norm=_ROI,
                      max_ai_fps=2.0, want_annotated=True)

    errors = []
    def background_inference():
        try:
            # force=True: fixture plumbing to enter single-flight under corrected budget
            svc.analyze_frame(camera_id=1, frame=_frame("f2"), face_pipeline=pipe,
                              roi_norm=_ROI, max_ai_fps=2.0, want_annotated=True,
                              force=True)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=background_inference)
    thread.start()
    try:
        assert pipe.entered.wait(timeout=3), "Overlapping inference setup did not start"
        snap, annotated = svc.analyze_frame(camera_id=1, frame=_frame("f3"),
                                            face_pipeline=pipe, roi_norm=_ROI,
                                            max_ai_fps=2.0, want_annotated=True)
        assert snap.frame_id == "f3", (
            f"Frame identity violation: input=f3, output snapshot={snap.frame_id}; "
            "must return fresh-frame metadata or explicit current-frame no-AI status"
        )
        if annotated is not None:
            assert snap.frame_id == "f3", "Annotated pixels may not be reused from an older frame"
    finally:
        pipe.release.set()
        thread.join(timeout=4)
    assert not errors, str(errors)
    assert not thread.is_alive()

"""Bounded LIVE face-detection preview — shared per-camera cache (detection+quality only).

No identity / similarity / attendance. No second RTSP capture.
Synthetic detector boxes are never returned as REAL overlay evidence.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.vision.faces.quality import MIN_FACE_WIDTH_PX, PREFERRED_FACE_WIDTH_PX
from app.vision.faces.types import FaceBox, InferenceMode, QualityReport


@dataclass
class LiveFaceDetectSnapshot:
    camera_id: int
    frame_id: str
    config_revision: str
    provenance: str
    decoder_status: str
    native_width: int
    native_height: int
    receive_time_utc: str | None
    status: str
    status_vi: str
    face_count: int
    faces: list[dict[str, Any]]
    quality: dict[str, Any]
    enrollment_gate: str
    enrollment_gate_vi: str
    min_face_width_px: int = MIN_FACE_WIDTH_PX
    preferred_face_width_px: int = PREFERRED_FACE_WIDTH_PX
    inference_mode: str = ""
    model_ready: bool = False
    cache_hit: bool = False
    ai_interval_s: float = 0.5
    outside_roi_count: int = 0
    roi: dict[str, float] | None = None
    identity_exposed: bool = False
    attendance_written: bool = False
    phase: str = "DETECTION_QUALITY_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "config_revision": self.config_revision,
            "provenance": self.provenance,
            "decoder_status": self.decoder_status,
            "native_width": self.native_width,
            "native_height": self.native_height,
            "receive_time_utc": self.receive_time_utc,
            "status": self.status,
            "status_vi": self.status_vi,
            "face_count": self.face_count,
            "faces": self.faces,
            "quality": self.quality,
            "enrollment_gate": self.enrollment_gate,
            "enrollment_gate_vi": self.enrollment_gate_vi,
            "min_face_width_px": self.min_face_width_px,
            "preferred_face_width_px": self.preferred_face_width_px,
            "inference_mode": self.inference_mode,
            "model_ready": self.model_ready,
            "cache_hit": self.cache_hit,
            "ai_interval_s": self.ai_interval_s,
            "outside_roi_count": self.outside_roi_count,
            "roi": self.roi,
            "identity_exposed": self.identity_exposed,
            "attendance_written": self.attendance_written,
            "phase": self.phase,
            "live_stability_pass": False,
            "camera_lab_pass": False,
            "face_pilot_pass": False,
        }


@dataclass
class _CacheEntry:
    mono: float
    frame_id: str
    snapshot: LiveFaceDetectSnapshot
    annotated_bgr: np.ndarray | None = None


class LiveFaceDetectPreviewService:
    """One shared inference budget per camera_id (not per browser viewer)."""

    def __init__(self, *, min_interval_s: float = 0.5, max_interval_s: float = 1.0) -> None:
        self._min_interval_s = float(min_interval_s)
        self._max_interval_s = float(max_interval_s)
        self._lock = threading.RLock()
        self._by_camera: dict[int, _CacheEntry] = {}
        self._inflight: set[int] = set()

    def clear_camera(self, camera_id: int) -> None:
        with self._lock:
            self._by_camera.pop(int(camera_id), None)

    def _interval(self, max_ai_fps: float) -> float:
        fps = max(1.0, min(float(max_ai_fps or 2.0), 3.0))
        return max(self._min_interval_s, min(1.0 / fps, self._max_interval_s))

    @staticmethod
    def _face_payload(box: FaceBox, *, native_w: int, native_h: int, roi: dict[str, float] | None) -> dict[str, Any]:
        nw = max(int(native_w), 1)
        nh = max(int(native_h), 1)
        cx = (box.x + box.w / 2.0) / nw
        cy = (box.y + box.h / 2.0) / nh
        outside = False
        if roi:
            rx, ry, rw, rh = float(roi["x"]), float(roi["y"]), float(roi["w"]), float(roi["h"])
            outside = not (rx <= cx <= rx + rw and ry <= cy <= ry + rh)
        return {
            "x_px": int(box.x),
            "y_px": int(box.y),
            "w_px": int(box.w),
            "h_px": int(box.h),
            "x_norm": round(box.x / nw, 6),
            "y_norm": round(box.y / nh, 6),
            "w_norm": round(box.w / nw, 6),
            "h_norm": round(box.h / nh, 6),
            "score": float(box.score),
            "inter_eye_px": float(box.inter_eye_px),
            "outside_roi": outside,
        }

    @staticmethod
    def _quality_dict(q: QualityReport) -> dict[str, Any]:
        pose = None
        if q.pose is not None:
            pose = {
                "yaw_deg": q.pose.yaw_deg,
                "pitch_deg": q.pose.pitch_deg,
                "roll_deg": q.pose.roll_deg,
                "slot_hint": q.pose.slot_hint,
                "confidence": q.pose.confidence,
            }
        return {
            "ok": bool(q.ok),
            "score": float(q.score),
            "face_width_px": int(q.face_width_px),
            "inter_eye_px": float(q.inter_eye_px),
            "blur_score": float(q.blur_score),
            "laplacian_var": float(q.laplacian_var),
            "hard_fail": bool(q.hard_fail),
            "reasons_vi": list(q.reasons_vi),
            "breakdown": dict(q.breakdown or {}),
            "pose": pose,
        }

    def _classify(
        self,
        *,
        faces: list[FaceBox],
        quality: QualityReport,
        model_ready: bool,
        inference_mode: str,
    ) -> tuple[str, str, str, str]:
        if not model_ready or inference_mode != InferenceMode.REAL.value:
            return (
                "NOT_READY",
                "Bộ phát hiện YuNet REAL chưa sẵn sàng — không dùng synthetic.",
                "NOT_READY",
                "Không đủ điều kiện ghi danh (model REAL chưa sẵn sàng).",
            )
        if not faces:
            return (
                "NO_FACE",
                quality.reasons_vi[0] if quality.reasons_vi else "Không thấy khuôn mặt.",
                "NO_FACE",
                "Cổng ghi danh: chưa có khuôn mặt.",
            )
        if len(faces) > 1:
            return (
                "MULTIPLE_FACES",
                "Phát hiện nhiều khuôn mặt — chỉ xem overlay; không ủy quyền chấm công nhiều người.",
                "MULTIPLE_FACES",
                "Cổng ghi danh: MULTIPLE_FACES (từ chối).",
            )
        if not quality.ok:
            state = str((quality.breakdown or {}).get("state") or "LOW_QUALITY")
            if "TOO_SMALL" in state or quality.face_width_px < MIN_FACE_WIDTH_PX:
                code = "FACE_TOO_SMALL"
            else:
                code = "LOW_QUALITY"
            return (
                code,
                quality.reasons_vi[0] if quality.reasons_vi else "Chất lượng khuôn mặt thấp.",
                code,
                f"Cổng ghi danh: {code}.",
            )
        return (
            "OK",
            "Phát hiện 1 khuôn mặt đạt chất lượng tối thiểu (detection+quality only).",
            "FACE_OK",
            "Cổng ghi danh: khuôn mặt đạt ngưỡng detection (chưa phải FACE_PILOT).",
        )

    def analyze_frame(
        self,
        *,
        camera_id: int,
        frame,
        face_pipeline: Any,
        roi_norm: dict[str, float] | None,
        max_ai_fps: float = 2.0,
        force: bool = False,
        want_annotated: bool = False,
    ) -> tuple[LiveFaceDetectSnapshot, np.ndarray | None]:
        """Run or reuse detection for this camera/frame. Clones pixels before any draw."""
        from app.vision.faces.annotate import annotate_detection_bgr

        cam_id = int(camera_id)
        interval = self._interval(max_ai_fps)
        now = time.monotonic()

        with self._lock:
            cached = self._by_camera.get(cam_id)
            if (
                not force
                and cached is not None
                and cached.frame_id == frame.frame_id
                and (now - cached.mono) < interval
            ):
                snap = cached.snapshot
                snap.cache_hit = True
                ann = cached.annotated_bgr
                if want_annotated and ann is None:
                    pixels = frame.clone_pixels()
                    boxes = [
                        FaceBox(
                            f["x_px"],
                            f["y_px"],
                            f["w_px"],
                            f["h_px"],
                            score=float(f.get("score") or 0),
                        )
                        for f in snap.faces
                    ]
                    ann = annotate_detection_bgr(
                        pixels,
                        boxes,
                        roi_norm=roi_norm,
                        status_label=snap.status,
                        primary_index=0 if boxes else None,
                    )
                    cached.annotated_bgr = ann
                return snap, ann if want_annotated else None

            if cam_id in self._inflight and cached is not None and not force:
                snap = cached.snapshot
                snap.cache_hit = True
                return snap, cached.annotated_bgr if want_annotated else None
            self._inflight.add(cam_id)

        try:
            mode = getattr(face_pipeline, "inference_mode", None)
            mode_v = mode.value if hasattr(mode, "value") else str(mode or "")
            det_info = getattr(getattr(face_pipeline, "detector", None), "info", None)
            model_ready = bool(getattr(det_info, "ready", False)) and mode_v == InferenceMode.REAL.value

            if frame.provenance.value == "MOCK":
                snap = LiveFaceDetectSnapshot(
                    camera_id=cam_id,
                    frame_id=frame.frame_id,
                    config_revision=frame.config_revision or "",
                    provenance=frame.provenance.value,
                    decoder_status=frame.decoder_status.value,
                    native_width=int(frame.width),
                    native_height=int(frame.height),
                    receive_time_utc=frame.receive_time_utc.isoformat() if frame.receive_time_utc else None,
                    status="REJECTED_MOCK",
                    status_vi="Nguồn MOCK — từ chối overlay detection thật.",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="REJECTED_MOCK",
                    enrollment_gate_vi="MOCK không đủ cho cổng detection LIVE.",
                    inference_mode=mode_v,
                    model_ready=model_ready,
                    ai_interval_s=interval,
                    roi=roi_norm,
                )
                ann = None
                if want_annotated:
                    ann = annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="REJECTED_MOCK"
                    )
            elif frame.decoder_status.value == "STALE":
                snap = LiveFaceDetectSnapshot(
                    camera_id=cam_id,
                    frame_id=frame.frame_id,
                    config_revision=frame.config_revision or "",
                    provenance=frame.provenance.value,
                    decoder_status=frame.decoder_status.value,
                    native_width=int(frame.width),
                    native_height=int(frame.height),
                    receive_time_utc=frame.receive_time_utc.isoformat() if frame.receive_time_utc else None,
                    status="STALE_FRAME",
                    status_vi="Khung STALE — không vẽ box giả lên luồng mới.",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="STALE_FRAME",
                    enrollment_gate_vi="Khung cũ — không dùng cho ghi danh.",
                    inference_mode=mode_v,
                    model_ready=model_ready,
                    ai_interval_s=interval,
                    roi=roi_norm,
                )
                ann = None
                if want_annotated:
                    ann = annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="STALE_FRAME"
                    )
            elif not model_ready:
                snap = LiveFaceDetectSnapshot(
                    camera_id=cam_id,
                    frame_id=frame.frame_id,
                    config_revision=frame.config_revision or "",
                    provenance=frame.provenance.value,
                    decoder_status=frame.decoder_status.value,
                    native_width=int(frame.width),
                    native_height=int(frame.height),
                    receive_time_utc=frame.receive_time_utc.isoformat() if frame.receive_time_utc else None,
                    status="NOT_READY",
                    status_vi="YuNet REAL chưa sẵn sàng (không fallback synthetic).",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="NOT_READY",
                    enrollment_gate_vi="Model REAL chưa sẵn sàng.",
                    inference_mode=mode_v,
                    model_ready=False,
                    ai_interval_s=interval,
                    roi=roi_norm,
                )
                ann = None
                if want_annotated:
                    ann = annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="NOT_READY"
                    )
            else:
                pixels = frame.clone_pixels()
                # Visualization may show many faces; enrollment gate still max_faces_ok=1
                faces, quality = face_pipeline.detect_and_quality(
                    pixels, max_faces_ok=1
                )
                status, status_vi, egate, egate_vi = self._classify(
                    faces=faces,
                    quality=quality,
                    model_ready=True,
                    inference_mode=mode_v,
                )
                face_payloads = [
                    self._face_payload(f, native_w=frame.width, native_h=frame.height, roi=roi_norm)
                    for f in faces
                ]
                outside = sum(1 for f in face_payloads if f.get("outside_roi"))
                if status == "OK" and outside:
                    status = "OUTSIDE_ROI"
                    status_vi = "Khuôn mặt ngoài vùng ROI arrival (draft/đã lưu)."
                    egate = "OUTSIDE_ROI"
                    egate_vi = "Cổng ghi danh: ngoài ROI."
                snap = LiveFaceDetectSnapshot(
                    camera_id=cam_id,
                    frame_id=frame.frame_id,
                    config_revision=frame.config_revision or "",
                    provenance=frame.provenance.value,
                    decoder_status=frame.decoder_status.value,
                    native_width=int(frame.width),
                    native_height=int(frame.height),
                    receive_time_utc=frame.receive_time_utc.isoformat() if frame.receive_time_utc else None,
                    status=status,
                    status_vi=status_vi,
                    face_count=len(faces),
                    faces=face_payloads,
                    quality=self._quality_dict(quality),
                    enrollment_gate=egate,
                    enrollment_gate_vi=egate_vi,
                    inference_mode=mode_v,
                    model_ready=True,
                    ai_interval_s=interval,
                    outside_roi_count=outside,
                    roi=roi_norm,
                )
                ann = None
                if want_annotated:
                    ann = annotate_detection_bgr(
                        pixels,
                        faces,
                        roi_norm=roi_norm,
                        status_label=status,
                        primary_index=0 if faces else None,
                    )

            with self._lock:
                self._by_camera[cam_id] = _CacheEntry(
                    mono=time.monotonic(),
                    frame_id=frame.frame_id,
                    snapshot=snap,
                    annotated_bgr=ann,
                )
            return snap, ann
        finally:
            with self._lock:
                self._inflight.discard(cam_id)


_default_service: LiveFaceDetectPreviewService | None = None
_default_lock = threading.Lock()


def get_live_face_detect_service() -> LiveFaceDetectPreviewService:
    global _default_service
    with _default_lock:
        if _default_service is None:
            _default_service = LiveFaceDetectPreviewService(min_interval_s=1.0 / 3.0, max_interval_s=1.0)
        return _default_service

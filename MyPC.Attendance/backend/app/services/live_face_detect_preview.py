"""Bounded LIVE face-detection preview — shared per-camera cache (detection+quality only).

P02-HF1: monotonic per-camera AI budget applies across distinct frame_ids, JSON and
annotated MJPEG viewers. At most one inference in flight per camera. Throttle/busy
responses carry the *current* source frame_id with empty faces — never relabel old
pixels/boxes as a newer frame.

No identity / similarity / attendance. No second RTSP capture.
Synthetic detector boxes are never returned as REAL overlay evidence.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.vision.faces.quality import MIN_FACE_WIDTH_PX, PREFERRED_FACE_WIDTH_PX
from app.vision.faces.types import FaceBox, InferenceMode, QualityReport

# Server-chosen AI budget ceiling (FPS). Clients may only lower the rate.
SERVER_AI_FPS_CAP = 2.0


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
    analyzed: bool = False
    prior_analyzed_frame_id: str | None = None
    browser_mjpeg_synchronized: bool = False
    last_analyzed_note_vi: str = (
        "JSON/AI stats là khung đã phân tích gần nhất — không đồng bộ tuyệt đối với từng frame <img> MJPEG."
    )

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
            "analyzed": self.analyzed,
            "prior_analyzed_frame_id": self.prior_analyzed_frame_id,
            "browser_mjpeg_synchronized": self.browser_mjpeg_synchronized,
            "last_analyzed_note_vi": self.last_analyzed_note_vi,
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
    config_revision: str = ""
    roi_fingerprint: str = ""


def _roi_fp(roi: dict[str, float] | None) -> str:
    if not roi:
        return ""
    return ",".join(f"{k}={float(roi.get(k, 0)):.6f}" for k in ("x", "y", "w", "h"))


class LiveFaceDetectPreviewService:
    """One shared inference budget per camera_id (not per browser viewer)."""

    def __init__(
        self,
        *,
        min_interval_s: float = 0.5,
        max_interval_s: float = 1.0,
        server_ai_fps_cap: float = SERVER_AI_FPS_CAP,
    ) -> None:
        self._min_interval_s = float(min_interval_s)
        self._max_interval_s = float(max_interval_s)
        # Deterministic server budget — clients cannot raise above this FPS.
        self._server_ai_fps_cap = max(1.0, min(float(server_ai_fps_cap or SERVER_AI_FPS_CAP), 3.0))
        self._lock = threading.RLock()
        self._by_camera: dict[int, _CacheEntry] = {}
        self._inflight: set[int] = set()
        self._generation: dict[int, int] = {}
        self._last_infer_mono: dict[int, float] = {}

    def clear_camera(self, camera_id: int) -> None:
        cam = int(camera_id)
        with self._lock:
            self._by_camera.pop(cam, None)
            self._last_infer_mono.pop(cam, None)
            self._generation[cam] = int(self._generation.get(cam, 0)) + 1
            # Do not remove inflight here — finishing task checks generation.

    def _interval(self, max_ai_fps: float) -> float:
        """Effective interval: clients may only lower rate below server cap."""
        req_fps = max(1.0, min(float(max_ai_fps or self._server_ai_fps_cap), 3.0))
        capped_fps = min(req_fps, self._server_ai_fps_cap)
        requested_interval = 1.0 / capped_fps
        return max(self._min_interval_s, min(requested_interval, self._max_interval_s))

    @staticmethod
    def _face_payload(
        box: FaceBox, *, native_w: int, native_h: int, roi: dict[str, float] | None
    ) -> dict[str, Any]:
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

    def _base_meta(self, *, camera_id: int, frame, interval: float, roi_norm, mode_v: str, model_ready: bool):
        return dict(
            camera_id=camera_id,
            frame_id=frame.frame_id,
            config_revision=frame.config_revision or "",
            provenance=frame.provenance.value,
            decoder_status=frame.decoder_status.value,
            native_width=int(frame.width),
            native_height=int(frame.height),
            receive_time_utc=frame.receive_time_utc.isoformat() if frame.receive_time_utc else None,
            inference_mode=mode_v,
            model_ready=model_ready,
            ai_interval_s=interval,
            roi=roi_norm,
            identity_exposed=False,
            attendance_written=False,
            browser_mjpeg_synchronized=False,
        )

    def _placeholder(
        self,
        *,
        camera_id: int,
        frame,
        interval: float,
        roi_norm,
        mode_v: str,
        model_ready: bool,
        status: str,
        status_vi: str,
        prior_frame_id: str | None,
        want_annotated: bool,
    ) -> tuple[LiveFaceDetectSnapshot, np.ndarray | None]:
        from app.vision.faces.annotate import annotate_detection_bgr

        snap = LiveFaceDetectSnapshot(
            **self._base_meta(
                camera_id=camera_id,
                frame=frame,
                interval=interval,
                roi_norm=roi_norm,
                mode_v=mode_v,
                model_ready=model_ready,
            ),
            status=status,
            status_vi=status_vi,
            face_count=0,
            faces=[],
            quality={},
            enrollment_gate=status,
            enrollment_gate_vi=status_vi,
            analyzed=False,
            prior_analyzed_frame_id=prior_frame_id,
            cache_hit=False,
        )
        ann = None
        if want_annotated:
            # Paint status on *current* frame pixels — never reuse older annotated_bgr.
            ann = annotate_detection_bgr(
                frame.clone_pixels(), [], roi_norm=roi_norm, status_label=status
            )
        return snap, ann

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
        """Run or reuse detection. Clones pixels before any draw. Frame identity always matches input."""
        from app.vision.faces.annotate import annotate_detection_bgr

        cam_id = int(camera_id)
        interval = self._interval(max_ai_fps)
        now = time.monotonic()
        mode = getattr(face_pipeline, "inference_mode", None)
        mode_v = mode.value if hasattr(mode, "value") else str(mode or "")
        det_info = getattr(getattr(face_pipeline, "detector", None), "info", None)
        model_ready = bool(getattr(det_info, "ready", False)) and mode_v == InferenceMode.REAL.value
        roi_key = _roi_fp(roi_norm)
        rev = frame.config_revision or ""

        with self._lock:
            cached = self._by_camera.get(cam_id)
            prior_id = cached.frame_id if cached is not None else None

            # Same-frame analyzed cache hit (config/ROI epoch must match).
            if (
                cached is not None
                and cached.frame_id == frame.frame_id
                and cached.config_revision == rev
                and cached.roi_fingerprint == roi_key
                and cached.snapshot.analyzed
            ):
                snap = LiveFaceDetectSnapshot(**{**cached.snapshot.__dict__})
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

            # Single-flight (even with force): never return another frame's snapshot as current.
            if cam_id in self._inflight:
                return self._placeholder(
                    camera_id=cam_id,
                    frame=frame,
                    interval=interval,
                    roi_norm=roi_norm,
                    mode_v=mode_v,
                    model_ready=model_ready,
                    status="AI_BUSY",
                    status_vi="AI đang xử lý khung khác — không gắn kết quả cũ lên frame hiện tại.",
                    prior_frame_id=prior_id,
                    want_annotated=want_annotated,
                )

            last_mono = float(self._last_infer_mono.get(cam_id, 0.0))
            # Global per-camera budget across DISTINCT frame_ids (HF1 fix).
            # force=True bypasses throttle only (tests / explicit catch-up), never single-flight.
            if not force and last_mono > 0 and (now - last_mono) < interval:
                return self._placeholder(
                    camera_id=cam_id,
                    frame=frame,
                    interval=interval,
                    roi_norm=roi_norm,
                    mode_v=mode_v,
                    model_ready=model_ready,
                    status="AI_THROTTLED",
                    status_vi=(
                        f"Ngân sách AI chia sẻ ~{1.0 / interval:.1f} FPS — "
                        "frame hiện tại chưa được phân tích (không dùng box khung cũ)."
                    ),
                    prior_frame_id=prior_id,
                    want_annotated=want_annotated,
                )

            self._inflight.add(cam_id)
            self._last_infer_mono[cam_id] = now
            gen = int(self._generation.get(cam_id, 0))

        try:
            if frame.provenance.value == "MOCK":
                snap = LiveFaceDetectSnapshot(
                    **self._base_meta(
                        camera_id=cam_id,
                        frame=frame,
                        interval=interval,
                        roi_norm=roi_norm,
                        mode_v=mode_v,
                        model_ready=model_ready,
                    ),
                    status="REJECTED_MOCK",
                    status_vi="Nguồn MOCK — từ chối overlay detection thật.",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="REJECTED_MOCK",
                    enrollment_gate_vi="MOCK không đủ cho cổng detection LIVE.",
                    analyzed=True,
                )
                ann = (
                    annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="REJECTED_MOCK"
                    )
                    if want_annotated
                    else None
                )
            elif frame.decoder_status.value == "STALE":
                snap = LiveFaceDetectSnapshot(
                    **self._base_meta(
                        camera_id=cam_id,
                        frame=frame,
                        interval=interval,
                        roi_norm=roi_norm,
                        mode_v=mode_v,
                        model_ready=model_ready,
                    ),
                    status="STALE_FRAME",
                    status_vi="Khung STALE — không vẽ box giả lên luồng mới.",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="STALE_FRAME",
                    enrollment_gate_vi="Khung cũ — không dùng cho ghi danh.",
                    analyzed=True,
                )
                ann = (
                    annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="STALE_FRAME"
                    )
                    if want_annotated
                    else None
                )
            elif not model_ready:
                snap = LiveFaceDetectSnapshot(
                    **self._base_meta(
                        camera_id=cam_id,
                        frame=frame,
                        interval=interval,
                        roi_norm=roi_norm,
                        mode_v=mode_v,
                        model_ready=False,
                    ),
                    status="NOT_READY",
                    status_vi="YuNet REAL chưa sẵn sàng (không fallback synthetic).",
                    face_count=0,
                    faces=[],
                    quality={},
                    enrollment_gate="NOT_READY",
                    enrollment_gate_vi="Model REAL chưa sẵn sàng.",
                    analyzed=True,
                )
                ann = (
                    annotate_detection_bgr(
                        frame.clone_pixels(), [], roi_norm=roi_norm, status_label="NOT_READY"
                    )
                    if want_annotated
                    else None
                )
            else:
                pixels = frame.clone_pixels()
                faces, quality = face_pipeline.detect_and_quality(pixels, max_faces_ok=1)
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
                    **self._base_meta(
                        camera_id=cam_id,
                        frame=frame,
                        interval=interval,
                        roi_norm=roi_norm,
                        mode_v=mode_v,
                        model_ready=True,
                    ),
                    status=status,
                    status_vi=status_vi,
                    face_count=len(faces),
                    faces=face_payloads,
                    quality=self._quality_dict(quality),
                    enrollment_gate=egate,
                    enrollment_gate_vi=egate_vi,
                    outside_roi_count=outside,
                    analyzed=True,
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
                if int(self._generation.get(cam_id, 0)) == gen:
                    self._by_camera[cam_id] = _CacheEntry(
                        mono=time.monotonic(),
                        frame_id=frame.frame_id,
                        snapshot=snap,
                        annotated_bgr=ann,
                        config_revision=rev,
                        roi_fingerprint=roi_key,
                    )
            return snap, ann
        except Exception:
            # Fail closed — current frame no-AI status, never leak prior boxes.
            snap, ann = self._placeholder(
                camera_id=cam_id,
                frame=frame,
                interval=interval,
                roi_norm=roi_norm,
                mode_v=mode_v,
                model_ready=model_ready,
                status="FRAME_NOT_ANALYZED",
                status_vi="Lỗi detector — không trả box khung cũ.",
                prior_frame_id=prior_id,
                want_annotated=want_annotated,
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
            _default_service = LiveFaceDetectPreviewService(
                min_interval_s=1.0 / 3.0,
                max_interval_s=1.0,
                server_ai_fps_cap=SERVER_AI_FPS_CAP,
            )
        return _default_service

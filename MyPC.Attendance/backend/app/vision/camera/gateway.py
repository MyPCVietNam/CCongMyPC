"""
CameraGateway — Live RTSP / recorded / mock with immutable frames and honest telemetry.

RealCam reliability: TCP-first open, HEVC keyframe wait after reconnect, corrupt-frame
guard, bounded exponential backoff with jitter, error classification, DEGRADED status.
Never invent clean frames. CONFIG_SAVED ≠ LIVE verified. CAMERA_LAB_PASS always False here.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

import numpy as np

logger = logging.getLogger("mypc.camera")

# Serialize OpenCV/FFmpeg open so process-global OPENCV_FFMPEG_CAPTURE_OPTIONS
# cannot race across simultaneous stream opens.
_FFMPEG_OPEN_LOCK = threading.Lock()


class StreamProvenance(str, Enum):
    CAMERA_LIVE = "CAMERA_LIVE"
    AUTHORIZED_RECORDED = "AUTHORIZED_RECORDED"
    MOCK = "MOCK"


class DecoderStatus(str, Enum):
    OK = "OK"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    CONNECTING = "CONNECTING"
    OFFLINE = "OFFLINE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"
    AUTH_FAILED = "AUTH_FAILED"
    STREAM_NOT_FOUND = "STREAM_NOT_FOUND"
    DECODE_FAILED = "DECODE_FAILED"


class ClockTrust(str, Enum):
    SERVER_RECEIVE = "SERVER_RECEIVE"
    DEVICE_PTS_UNVERIFIED = "DEVICE_PTS_UNVERIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CameraFrame:
    """Immutable decoded BGR: pixels held as raw bytes (not a writable ndarray alias)."""

    frame_id: str
    camera_id: str
    width: int
    height: int
    capture_time_utc: datetime
    receive_time_utc: datetime
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    _pixels: bytes = field(repr=False, compare=False)
    estimated_skew_ms: float = 0.0
    source_event_id: str = ""
    config_revision: str = ""
    clock_trust: ClockTrust = ClockTrust.SERVER_RECEIVE
    pixel_sha256: str = ""
    receive_monotonic: float = 0.0
    integrity_ok: bool = True

    @staticmethod
    def from_bgr(
        bgr: np.ndarray,
        *,
        frame_id: str,
        camera_id: str,
        capture_time_utc: datetime,
        receive_time_utc: datetime,
        provenance: StreamProvenance,
        decoder_status: DecoderStatus,
        estimated_skew_ms: float = 0.0,
        source_event_id: str = "",
        config_revision: str = "",
        clock_trust: ClockTrust = ClockTrust.SERVER_RECEIVE,
        receive_monotonic: float | None = None,
        integrity_ok: bool = True,
    ) -> "CameraFrame":
        if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("expected uint8 HxWx3 BGR")
        h, w = int(bgr.shape[0]), int(bgr.shape[1])
        raw = np.ascontiguousarray(bgr).tobytes()
        import hashlib

        digest = hashlib.sha256(raw).hexdigest()
        return CameraFrame(
            frame_id=frame_id,
            camera_id=camera_id,
            width=w,
            height=h,
            capture_time_utc=capture_time_utc,
            receive_time_utc=receive_time_utc,
            provenance=provenance,
            decoder_status=decoder_status,
            _pixels=raw,
            estimated_skew_ms=estimated_skew_ms,
            source_event_id=source_event_id,
            config_revision=config_revision,
            clock_trust=clock_trust,
            pixel_sha256=digest,
            receive_monotonic=float(receive_monotonic if receive_monotonic is not None else time.monotonic()),
            integrity_ok=integrity_ok,
        )

    @property
    def bgr(self) -> np.ndarray:
        arr = np.frombuffer(self._pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
        return arr

    def clone_pixels(self) -> np.ndarray:
        return np.frombuffer(self._pixels, dtype=np.uint8).reshape(self.height, self.width, 3).copy()

    def with_status(self, status: DecoderStatus) -> "CameraFrame":
        return CameraFrame(
            frame_id=self.frame_id,
            camera_id=self.camera_id,
            width=self.width,
            height=self.height,
            capture_time_utc=self.capture_time_utc,
            receive_time_utc=self.receive_time_utc,
            provenance=self.provenance,
            decoder_status=status,
            _pixels=self._pixels,
            estimated_skew_ms=self.estimated_skew_ms,
            source_event_id=self.source_event_id,
            config_revision=self.config_revision,
            clock_trust=self.clock_trust,
            pixel_sha256=self.pixel_sha256,
            receive_monotonic=self.receive_monotonic,
            integrity_ok=self.integrity_ok,
        )


@dataclass
class GatewayHealth:
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    native_width: int = 0
    native_height: int = 0
    fps_estimate: float = 0.0
    dropped_frames: int = 0
    decode_errors: int = 0
    stale_frames: int = 0
    reconnect_count: int = 0
    last_frame_at: datetime | None = None
    detail_vi: str = ""
    camera_lab_pass: bool = False
    operationally_ready: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


def frame_looks_corrupt(bgr: np.ndarray) -> bool:
    """Cheap IMAGE-STATISTIC heuristic — not RTP/HEVC bitstream proof (P1-04).

    Rejects empty / mostly-black / near-constant slabs. Damaged partial frames can
    evade this; treat as necessary but insufficient. Real CAMERA_LAB still needs
    owner A/B evidence. Does NOT invent a clean substitute.
    """
    if bgr is None or not isinstance(bgr, np.ndarray) or bgr.size == 0:
        return True
    h, w = bgr.shape[:2]
    if h < 16 or w < 16:
        return True
    # Sample a coarse grid for speed on 2880x1620
    step_y = max(1, h // 48)
    step_x = max(1, w // 48)
    sample = bgr[::step_y, ::step_x]
    mean = float(sample.mean())
    std = float(sample.std())
    if mean < 2.0 and std < 2.0:
        return True
    if std < 0.5:
        return True
    # Large contiguous zero rows (common HEVC ref-loss artifact)
    row_means = bgr[:: max(1, h // 64), :, :].mean(axis=(1, 2))
    zeroish = float((row_means < 1.5).mean())
    if zeroish > 0.35:
        return True
    return False


def physical_stream_fingerprint(rtsp_uri: str) -> str:
    """Stable key for unique physical stream (host:port/path) — never includes credentials."""
    try:
        p = urlparse(rtsp_uri)
        host = (p.hostname or "").lower()
        port = p.port or (554 if (p.scheme or "").lower() == "rtsp" else 0)
        path = p.path or "/"
        return f"{host}:{port}{path}"
    except Exception:
        return "unknown"


class CameraGateway(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def get_latest_frame(self) -> CameraFrame | None: ...

    @abstractmethod
    def health(self) -> GatewayHealth: ...


class MockFrameGateway(CameraGateway):
    def __init__(self, camera_id: str = "mock-0", width: int = 640, height: int = 360) -> None:
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self._running = False
        self._idx = 0
        self.config_revision = str(uuid.uuid4())

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def get_latest_frame(self) -> CameraFrame | None:
        if not self._running:
            return None
        self._idx += 1
        img = np.full((self.height, self.width, 3), 40 + (self._idx % 80), dtype=np.uint8)
        now = datetime.now(timezone.utc)
        return CameraFrame.from_bgr(
            img,
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.MOCK,
            decoder_status=DecoderStatus.OK,
            source_event_id=f"mock-{self._idx}",
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
        )

    def health(self) -> GatewayHealth:
        ok = self._running
        return GatewayHealth(
            provenance=StreamProvenance.MOCK,
            decoder_status=DecoderStatus.OK if ok else DecoderStatus.OFFLINE,
            native_width=self.width,
            native_height=self.height,
            detail_vi="Chế độ MOCK — không phải camera thật; CAMERA_LAB_PASS=false.",
            camera_lab_pass=False,
            operationally_ready=False,
            extras={"connection_status": "MOCK", "live_decoded": False},
        )


class AuthorizedRecordedVideoGateway(CameraGateway):
    def __init__(self, path: str, camera_id: str = "recorded-0") -> None:
        self.path = path
        self.camera_id = camera_id
        self._cap = None
        self.config_revision = str(uuid.uuid4())
        self._lock = threading.Lock()

    def start(self) -> None:
        import cv2

        self._cap = cv2.VideoCapture(self.path)
        if not self._cap.isOpened():
            logger.warning("recorded_video_open_failed")
            self._cap = None

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def get_latest_frame(self) -> CameraFrame | None:
        if self._cap is None:
            return None
        import cv2

        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok or frame is None:
                return None
        now = datetime.now(timezone.utc)
        return CameraFrame.from_bgr(
            frame,
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
        )

    def health(self) -> GatewayHealth:
        ok = self._cap is not None and self._cap.isOpened()
        return GatewayHealth(
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK if ok else DecoderStatus.OFFLINE,
            detail_vi="Video ghi hình được ủy quyền — không phải luồng LIVE.",
            camera_lab_pass=False,
            operationally_ready=False,
        )


class LiveRTSPGateway(CameraGateway):
    """One owned decode loop per gateway instance — prefer leasing via CameraSourceRegistry."""

    def __init__(
        self,
        rtsp_uri: str,
        camera_id: str = "live-0",
        *,
        max_backoff_s: float = 30.0,
        stale_after_s: float = 3.0,
        config_revision: str | None = None,
        max_reconnect_attempts: int = 12,
        transport: str = "tcp",
        keyframe_warmup_frames: int = 8,
        good_frame_streak_needed: int = 3,
    ) -> None:
        self._uri = rtsp_uri
        self.camera_id = camera_id
        self._max_backoff = max_backoff_s
        self._stale_after = stale_after_s
        self._max_reconnect_attempts = max(1, int(max_reconnect_attempts))
        self._transport = (transport or "tcp").lower()
        self._keyframe_warmup = max(0, int(keyframe_warmup_frames))
        self._good_streak_needed = max(1, int(good_frame_streak_needed))
        self.config_revision = config_revision or str(uuid.uuid4())
        self.stream_fingerprint = physical_stream_fingerprint(rtsp_uri)
        self._cap = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._latest_good: CameraFrame | None = None
        self._overwritten_latest = 0
        self._decode_errors = 0
        self._corrupt_frames = 0
        self._hevc_ref_events = 0  # image-stat heuristic only — NOT native FFmpeg POC counts
        self._reconnects = 0  # consecutive failure budget
        self._lifetime_reconnect_attempts = 0
        self._reconnect_successes = 0
        self._recovery_duration_ms_last = 0.0
        self._status = DecoderStatus.NOT_CONFIGURED
        self._last_error_class = "UNKNOWN"
        self._native = (0, 0)
        self._cap_prop_hint = (0, 0)
        self._buffersize_set_ok: bool | None = None
        self._recv_times: deque[float] = deque(maxlen=60)
        self._frames_ok = 0
        self._frames_published = 0
        self._warmup_remaining = 0
        self._good_streak = 0
        self._fail_started_mono: float | None = None
        self._last_good_mono: float | None = None
        self._open_latency_ms = 0.0
        self._read_latency_ms = 0.0
        self._stale_served = 0
        self._corrupt_streak = 0

    def start(self) -> None:
        with self._start_lock:
            if not self._uri:
                self._status = DecoderStatus.NOT_CONFIGURED
                return
            # Refuse a second reader while a prior worker is still alive (P1-05)
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name=f"rtsp-{self.camera_id}", daemon=True
            )
            self._thread.start()

    def stop(self, *, join_timeout_s: float | None = None) -> None:
        self._stop.set()
        thr = self._thread
        alive_after = False
        timeout = 5.0 if join_timeout_s is None else float(join_timeout_s)
        if thr is not None and thr.is_alive():
            thr.join(timeout=timeout)
            alive_after = thr.is_alive()
        with self._start_lock:
            if alive_after:
                # Do NOT clear _thread or release while reader may still block in read()
                with self._lock:
                    self._latest = None
                    self._latest_good = None
                    self._status = DecoderStatus.STOPPED
                    self._last_error_class = "STOP_JOIN_TIMEOUT"
                return
            self._thread = None
        self._release()
        with self._lock:
            self._latest = None
            self._latest_good = None
            self._status = DecoderStatus.OFFLINE

    def invalidate(self) -> None:
        with self._lock:
            self._latest = None
            self._latest_good = None
            self.config_revision = str(uuid.uuid4())

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _ffmpeg_options_for_transport(self) -> str:
        """Prefer TCP interleaved as first controlled transport — overridable via env."""
        # Do not set skip_frame / nobuffer globally without A/B evidence.
        transport = self._transport if self._transport in {"tcp", "udp"} else "tcp"
        return os.environ.get("MYPC_FFMPEG_CAPTURE_OPTIONS") or (
            f"rtsp_transport;{transport}|stimeout;5000000"
        )

    def _reset_session_fps_window(self) -> None:
        """Drop cross-session recv timestamps so FPS is not diluted by reconnect gaps."""
        self._recv_times.clear()

    def _open(self) -> bool:
        import cv2

        self._status = DecoderStatus.CONNECTING
        # Clear prior good frames — never leave a stale good buffer across reopen
        with self._lock:
            self._latest_good = None
            self._reset_session_fps_window()
        t0 = time.monotonic()
        with _FFMPEG_OPEN_LOCK:
            prev = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = self._ffmpeg_options_for_transport()
            try:
                self._cap = cv2.VideoCapture(self._uri, cv2.CAP_FFMPEG)
            finally:
                if prev is None:
                    os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
                else:
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = prev
        # CAP_PROP_BUFFERSIZE after open is best-effort — FFmpeg RTSP often ignores it.
        self._buffersize_set_ok = None
        try:
            if self._cap is not None:
                self._buffersize_set_ok = bool(self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 2))
        except Exception:
            self._buffersize_set_ok = False
        ok = bool(self._cap is not None and self._cap.isOpened())
        self._open_latency_ms = (time.monotonic() - t0) * 1000.0
        if not ok:
            logger.warning(
                "rtsp_open_failed camera_id=%s config_revision=%s transport=%s",
                self.camera_id,
                self.config_revision[:8] if self.config_revision else "",
                self._transport,
            )
            self._release()
            self._status = DecoderStatus.OFFLINE
            self._last_error_class = "OPEN_FAILED"
            with self._lock:
                self._reset_session_fps_window()
            if self._fail_started_mono is None:
                self._fail_started_mono = time.monotonic()
            return False
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._cap_prop_hint = (w, h)
        self._warmup_remaining = self._keyframe_warmup
        self._good_streak = 0
        self._status = DecoderStatus.CONNECTING
        self._last_error_class = ""
        return True

    def _measured_fps(self) -> float | None:
        """Session-scoped FPS. None = UNKNOWN / insufficient samples (not 0.0 fabrication)."""
        if len(self._recv_times) < 2:
            return None
        dt = self._recv_times[-1] - self._recv_times[0]
        if dt <= 0:
            return None
        # Guard: span longer than session window implies stale samples across a gap
        if dt > 8.0 and len(self._recv_times) < 8:
            return None
        return float((len(self._recv_times) - 1) / dt)

    def _sleep_backoff(self, backoff: float) -> float:
        # Exponential + jitter; never spin hot
        jitter = random.uniform(0.0, min(0.75, backoff * 0.25))
        end = time.monotonic() + backoff + jitter
        while time.monotonic() < end and not self._stop.is_set():
            time.sleep(0.1)
        return min(self._max_backoff, backoff * 1.7 + 0.15)

    def _publish(self, fr: CameraFrame, *, good: bool) -> None:
        with self._lock:
            if self._latest is not None:
                self._overwritten_latest += 1
            self._latest = fr
            self._frames_published += 1
            if good:
                # Count recovery if we were in a failure window
                if self._fail_started_mono is not None:
                    self._recovery_duration_ms_last = (
                        time.monotonic() - self._fail_started_mono
                    ) * 1000.0
                    self._reconnect_successes += 1
                self._latest_good = fr
                self._recv_times.append(fr.receive_monotonic)
                self._frames_ok += 1
                self._last_good_mono = fr.receive_monotonic
                self._fail_started_mono = None
                self._status = DecoderStatus.OK
                self._last_error_class = ""
                self._reconnects = 0  # consecutive budget only
                self._corrupt_streak = 0
            else:
                self._latest_good = None
                self._status = DecoderStatus.DEGRADED
                if not self._last_error_class:
                    self._last_error_class = "CORRUPT_OR_WARMUP"

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._cap is None and not self._open():
                self._reconnects += 1
                self._lifetime_reconnect_attempts += 1
                if self._reconnects >= self._max_reconnect_attempts:
                    self._status = DecoderStatus.STOPPED
                    self._last_error_class = "RECONNECT_EXHAUSTED"
                    logger.warning(
                        "rtsp_reconnect_exhausted camera_id=%s attempts=%s",
                        self.camera_id,
                        self._reconnects,
                    )
                    break
                self._status = DecoderStatus.RECONNECTING
                backoff = self._sleep_backoff(backoff)
                continue
            backoff = 1.0
            assert self._cap is not None
            t_read = time.monotonic()
            ok, frame = self._cap.read()
            self._read_latency_ms = (time.monotonic() - t_read) * 1000.0
            recv_mono = time.monotonic()
            recv = datetime.now(timezone.utc)
            if not ok or frame is None:
                self._decode_errors += 1
                # Generic read/decode failure — do NOT inflate hevc_ref_events (P1-04)
                # Native FFmpeg POC/cu_qp_delta stderr is NOT captured here → UNAVAILABLE.
                self._reconnects += 1  # decode-fail reopen counts toward budget (R09)
                self._lifetime_reconnect_attempts += 1
                self._status = DecoderStatus.RECONNECTING
                self._last_error_class = "DECODE_FAILED"
                self._corrupt_streak = 0
                if self._fail_started_mono is None:
                    self._fail_started_mono = recv_mono
                with self._lock:
                    self._latest_good = None
                    self._reset_session_fps_window()
                self._release()
                if self._reconnects >= self._max_reconnect_attempts:
                    self._status = DecoderStatus.STOPPED
                    self._last_error_class = "RECONNECT_EXHAUSTED"
                    logger.warning(
                        "rtsp_decode_fail_exhausted camera_id=%s attempts=%s",
                        self.camera_id,
                        self._reconnects,
                    )
                    break
                backoff = self._sleep_backoff(backoff)
                continue

            corrupt = frame_looks_corrupt(frame)
            if self._warmup_remaining > 0:
                self._warmup_remaining -= 1
                # Discard mid-GOP warmup frames — do not publish as healthy LIVE
                if corrupt:
                    self._corrupt_frames += 1
                    self._hevc_ref_events += 1  # heuristic counter only
                    self._good_streak = 0
                    self._corrupt_streak += 1
                else:
                    self._good_streak += 1
                    self._corrupt_streak = 0
                if self._warmup_remaining > 0 or self._good_streak < self._good_streak_needed:
                    self._status = DecoderStatus.CONNECTING
                    # Avoid hot-spin during warmup/corrupt (S5)
                    if corrupt:
                        time.sleep(min(0.25, 0.05 * max(1, self._corrupt_streak)))
                    continue

            if corrupt:
                self._corrupt_frames += 1
                self._hevc_ref_events += 1  # image-stat only — not FFmpeg stderr POC proof
                self._good_streak = 0
                self._corrupt_streak += 1
                if self._fail_started_mono is None:
                    self._fail_started_mono = recv_mono
                # Sustained corrupt pause can dilute session FPS — rebase window (HF2)
                if self._corrupt_streak >= 3:
                    with self._lock:
                        self._reset_session_fps_window()
                # Invalidate last good — biometric must not reuse pre-corruption frame
                with self._lock:
                    self._latest_good = None
                # Wait for next independently decodable keyframe window
                self._warmup_remaining = max(2, self._keyframe_warmup // 2)
                h, w = frame.shape[:2]
                self._native = (w, h)
                self._last_error_class = "SUSPECTED_CORRUPT_FRAME"
                # Publish DEGRADED only for UI honesty — biometric paths must reject integrity_ok=False
                try:
                    fr_bad = CameraFrame.from_bgr(
                        frame,
                        frame_id=str(uuid.uuid4()),
                        camera_id=self.camera_id,
                        capture_time_utc=recv,
                        receive_time_utc=recv,
                        provenance=StreamProvenance.CAMERA_LIVE,
                        decoder_status=DecoderStatus.DEGRADED,
                        source_event_id=str(uuid.uuid4()),
                        config_revision=self.config_revision,
                        clock_trust=ClockTrust.SERVER_RECEIVE,
                        receive_monotonic=recv_mono,
                        integrity_ok=False,
                    )
                    self._publish(fr_bad, good=False)
                except Exception:
                    self._status = DecoderStatus.DEGRADED
                # Bound CPU during sustained corrupt slabs (S5)
                time.sleep(min(0.5, 0.05 * max(1, self._corrupt_streak)))
                continue

            self._good_streak += 1
            h, w = frame.shape[:2]
            self._native = (w, h)
            fr = CameraFrame.from_bgr(
                frame,
                frame_id=str(uuid.uuid4()),
                camera_id=self.camera_id,
                capture_time_utc=recv,
                receive_time_utc=recv,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                source_event_id=str(uuid.uuid4()),
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=recv_mono,
                integrity_ok=True,
            )
            self._publish(fr, good=True)

    def get_latest_frame(self) -> CameraFrame | None:
        with self._lock:
            fr = self._latest
            if fr is None:
                return None
            age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
            # Prefer gateway truth over a leftover OK frame while reconnecting (S6)
            if self._status in {
                DecoderStatus.RECONNECTING,
                DecoderStatus.CONNECTING,
                DecoderStatus.OFFLINE,
                DecoderStatus.STOPPED,
                DecoderStatus.DECODE_FAILED,
            }:
                self._stale_served += 1
                return fr.with_status(
                    DecoderStatus.STALE
                    if self._status
                    in {DecoderStatus.RECONNECTING, DecoderStatus.CONNECTING}
                    else self._status
                )
            if age > self._stale_after:
                self._stale_served += 1
                return fr.with_status(DecoderStatus.STALE)
            return fr

    def get_latest_good_frame(self) -> CameraFrame | None:
        """Last integrity-ok frame — None while decoder is unhealthy (no silent reuse)."""
        with self._lock:
            if self._status in {
                DecoderStatus.DEGRADED,
                DecoderStatus.RECONNECTING,
                DecoderStatus.CONNECTING,
                DecoderStatus.OFFLINE,
                DecoderStatus.STOPPED,
                DecoderStatus.AUTH_FAILED,
                DecoderStatus.STREAM_NOT_FOUND,
                DecoderStatus.DECODE_FAILED,
                DecoderStatus.NOT_CONFIGURED,
                DecoderStatus.BLOCKED,
            }:
                return None
            fr = self._latest_good
            if fr is None:
                return None
            age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
            if age > self._stale_after:
                return fr.with_status(DecoderStatus.STALE)
            if not getattr(fr, "integrity_ok", True):
                return None
            return fr

    def health(self) -> GatewayHealth:
        with self._lock:
            last = self._latest.receive_time_utc if self._latest else None
            status = self._status
            if self._latest is not None:
                age = (datetime.now(timezone.utc) - self._latest.receive_time_utc).total_seconds()
                if age > self._stale_after and status == DecoderStatus.OK:
                    status = DecoderStatus.STALE
            overwritten = self._overwritten_latest
            decode_errors = self._decode_errors
            corrupt = self._corrupt_frames
            hevc_ref = self._hevc_ref_events
            reconnects = self._reconnects
            lifetime_reconn = self._lifetime_reconnect_attempts
            reconn_ok = self._reconnect_successes
            recovery_ms = self._recovery_duration_ms_last
            stale_served = self._stale_served
            buf_ok = self._buffersize_set_ok
            w, h = self._native
            fps = self._measured_fps()
            hint = self._cap_prop_hint
            err = self._last_error_class
            frames_ok = self._frames_ok
            fail_dur = (
                (time.monotonic() - self._fail_started_mono) if self._fail_started_mono else 0.0
            )
            age_good = (
                (time.monotonic() - self._last_good_mono) if self._last_good_mono else None
            )
            open_ms = self._open_latency_ms
            read_ms = self._read_latency_ms
            transport = self._transport
            fp = self.stream_fingerprint
            frame_age_ms = None
            if last is not None:
                frame_age_ms = round(
                    (datetime.now(timezone.utc) - last).total_seconds() * 1000.0, 1
                )
        ready = status == DecoderStatus.OK and bool(w and h) and frames_ok > 0
        fps_display = round(fps, 3) if fps is not None else 0.0
        fps_status = "MEASURED" if fps is not None else "UNKNOWN_INSUFFICIENT_SAMPLES"
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=status,
            native_width=w,
            native_height=h,
            fps_estimate=fps_display,
            dropped_frames=overwritten,
            decode_errors=decode_errors,
            stale_frames=stale_served,
            reconnect_count=reconnects,
            last_frame_at=last,
            detail_vi=(
                f"camera_id={self.camera_id}; RTSP trạng thái={status.value}; "
                f"DECODED_MEASURED={w}x{h}; FPS={fps_status}"
                f"{'' if fps is None else f'={fps:.2f}'}; frames_ok={frames_ok}; "
                f"suspected_corrupt={corrupt}; transport={transport}; "
                f"last_error={err or 'none'}; native_ffmpeg_errors=UNAVAILABLE. "
                "CONFIG_SAVED ≠ LIVE verified. CAMERA_LAB_PASS=false. "
                "Dark/IR may trip image-stat corrupt heuristic — not native HEVC proof."
            ),
            camera_lab_pass=False,
            operationally_ready=ready,
            extras={
                "size_source": "DECODED_MEASURED" if w and h else "UNVERIFIED",
                "cap_prop_hint_wh": list(hint),
                "cap_prop_buffersize_set_ok": buf_ok,
                "overwritten_latest": overwritten,
                "decode_errors": decode_errors,
                "decode_read_failures": decode_errors,
                "corrupt_frames": corrupt,
                "suspected_corrupt_frames": corrupt,
                # Legacy name kept; MUST NOT be read as native FFmpeg POC/cu_qp_delta proof
                "hevc_ref_events": hevc_ref,
                "hevc_ref_events_meaning": "image_stat_heuristic_only",
                "native_decoder_error_category": "UNAVAILABLE",
                "source_fps_measured": fps,
                "source_fps_status": fps_status,
                "frame_age_ms": frame_age_ms,
                "clock_trust": ClockTrust.SERVER_RECEIVE.value,
                "diagnostic_uri": "REDACTED",
                "operationally_ready": ready,
                "last_error_class": err or "",
                "frames_ok": frames_ok,
                "distinct_frames": frames_ok,
                "live_decoded": bool(frames_ok > 0 and ready),
                "transport": transport,
                "stream_fingerprint": fp,
                "fail_duration_s": round(fail_dur, 3),
                "time_since_last_good_frame_s": (
                    None if age_good is None else round(age_good, 3)
                ),
                "age_newest_good_s": None if age_good is None else round(age_good, 3),
                "open_latency_ms": round(open_ms, 2),
                "read_latency_ms": round(read_ms, 2),
                "reconnect_attempts_lifetime": lifetime_reconn,
                "reconnect_successes": reconn_ok,
                "recovery_duration_ms_last": round(recovery_ms, 2),
                "stale_frames_served": stale_served,
                "connection_status": (
                    "LIVE_DECODED"
                    if ready
                    else (
                        "STOPPED"
                        if status == DecoderStatus.STOPPED
                        else (
                            "DEGRADED"
                            if status == DecoderStatus.DEGRADED
                            else (
                                "CONNECTING"
                                if status
                                in {DecoderStatus.RECONNECTING, DecoderStatus.CONNECTING}
                                else (
                                    "CONFIG_SAVED"
                                    if status == DecoderStatus.OK and frames_ok == 0
                                    else status.value
                                )
                            )
                        )
                    )
                ),
            },
        )


def sanitize_rtsp_for_log(uri: str) -> str:
    """Deprecated for exports — strips userinfo but path may still leak. Prefer REDACTED."""
    try:
        p = urlparse(uri)
        netloc = p.hostname or ""
        if p.port:
            netloc = f"{netloc}:{p.port}"
        return urlunparse((p.scheme, netloc, "/<redacted>", "", "", ""))
    except Exception:
        return "REDACTED"

"""
CameraGateway — Live RTSP / recorded / mock with immutable frames and honest telemetry.

P02-HF: defensive BGR copies, measured FPS, overwritten_latest ≠ network loss,
idempotent start/stop, SERVER_RECEIVE clock label, sanitized diagnostics only.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger("mypc.camera")


class StreamProvenance(str, Enum):
    CAMERA_LIVE = "CAMERA_LIVE"
    AUTHORIZED_RECORDED = "AUTHORIZED_RECORDED"
    MOCK = "MOCK"


class DecoderStatus(str, Enum):
    OK = "OK"
    STALE = "STALE"
    RECONNECTING = "RECONNECTING"
    OFFLINE = "OFFLINE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    BLOCKED = "BLOCKED"


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
        )

    @property
    def bgr(self) -> np.ndarray:
        """Read-only view over immutable bytes — setflags(write=True) cannot alias-mutate storage."""
        arr = np.frombuffer(self._pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
        return arr

    def clone_pixels(self) -> np.ndarray:
        """Owned writable copy for preview/enhance/align consumers."""
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
        )


@dataclass
class GatewayHealth:
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    native_width: int = 0
    native_height: int = 0
    fps_estimate: float = 0.0  # measured rolling receive FPS
    dropped_frames: int = 0  # overwritten_latest count (app-level)
    decode_errors: int = 0
    stale_frames: int = 0
    reconnect_count: int = 0
    last_frame_at: datetime | None = None
    detail_vi: str = ""
    camera_lab_pass: bool = False
    operationally_ready: bool = False  # False when STALE/OFFLINE/RECONNECTING
    extras: dict[str, Any] = field(default_factory=dict)


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
            operationally_ready=False,  # MOCK never operational LIVE
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
    def __init__(
        self,
        rtsp_uri: str,
        camera_id: str = "live-0",
        *,
        max_backoff_s: float = 30.0,
        stale_after_s: float = 3.0,
        config_revision: str | None = None,
    ) -> None:
        self._uri = rtsp_uri
        self.camera_id = camera_id
        self._max_backoff = max_backoff_s
        self._stale_after = stale_after_s
        self.config_revision = config_revision or str(uuid.uuid4())
        self._cap = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._overwritten_latest = 0
        self._decode_errors = 0
        self._reconnects = 0
        self._status = DecoderStatus.NOT_CONFIGURED
        self._native = (0, 0)  # DECODED_MEASURED only after successful frame
        self._cap_prop_hint = (0, 0)
        self._recv_times: deque[float] = deque(maxlen=60)

    def start(self) -> None:
        with self._start_lock:
            if not self._uri:
                self._status = DecoderStatus.NOT_CONFIGURED
                return
            if self._thread is not None and self._thread.is_alive():
                return  # idempotent
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name=f"rtsp-{self.camera_id}", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thr = self._thread
        if thr is not None and thr.is_alive():
            thr.join(timeout=5)
        with self._start_lock:
            self._thread = None
        self._release()
        with self._lock:
            self._latest = None  # invalidate on stop/reconfig
            self._status = DecoderStatus.OFFLINE

    def invalidate(self) -> None:
        """Called on reconfig — drop latest so no stale cross-camera use."""
        with self._lock:
            self._latest = None
            self.config_revision = str(uuid.uuid4())

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _open(self) -> bool:
        import cv2

        self._cap = cv2.VideoCapture(self._uri, cv2.CAP_FFMPEG)
        ok = bool(self._cap.isOpened())
        if not ok:
            logger.warning("rtsp_open_failed camera_id=%s", self.camera_id)
            self._release()
            self._status = DecoderStatus.OFFLINE
            return False
        self._status = DecoderStatus.OK
        # CAP_PROP hints only — not DECODED_MEASURED
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._cap_prop_hint = (w, h)
        return True

    def _measured_fps(self) -> float:
        if len(self._recv_times) < 2:
            return 0.0
        dt = self._recv_times[-1] - self._recv_times[0]
        if dt <= 0:
            return 0.0
        return float((len(self._recv_times) - 1) / dt)

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._cap is None and not self._open():
                self._status = DecoderStatus.RECONNECTING
                self._reconnects += 1
                # Interruptible backoff
                end = time.monotonic() + backoff
                while time.monotonic() < end and not self._stop.is_set():
                    time.sleep(0.1)
                backoff = min(self._max_backoff, backoff * 1.7 + 0.1)
                continue
            backoff = 1.0
            assert self._cap is not None
            ok, frame = self._cap.read()
            recv_mono = time.monotonic()
            recv = datetime.now(timezone.utc)
            if not ok or frame is None:
                self._decode_errors += 1
                self._status = DecoderStatus.RECONNECTING
                self._release()
                continue
            h, w = frame.shape[:2]
            self._native = (w, h)  # DECODED_MEASURED
            fr = CameraFrame.from_bgr(
                frame,
                frame_id=str(uuid.uuid4()),
                camera_id=self.camera_id,
                capture_time_utc=recv,  # SERVER_RECEIVE — not device PTS
                receive_time_utc=recv,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                source_event_id=str(uuid.uuid4()),
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=recv_mono,
            )
            with self._lock:
                if self._latest is not None:
                    self._overwritten_latest += 1
                self._latest = fr
                self._recv_times.append(recv_mono)
                self._status = DecoderStatus.OK

    def get_latest_frame(self) -> CameraFrame | None:
        with self._lock:
            fr = self._latest
            if fr is None:
                return None
            age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
            if age > self._stale_after:
                return fr.with_status(DecoderStatus.STALE)
            return fr

    def health(self) -> GatewayHealth:
        with self._lock:
            last = self._latest.receive_time_utc if self._latest else None
            status = self._status
            if self._latest is not None:
                age = (datetime.now(timezone.utc) - self._latest.receive_time_utc).total_seconds()
                if age > self._stale_after:
                    status = DecoderStatus.STALE
            overwritten = self._overwritten_latest
            decode_errors = self._decode_errors
            reconnects = self._reconnects
            w, h = self._native
            fps = self._measured_fps()
            hint = self._cap_prop_hint
        ready = status == DecoderStatus.OK and bool(w and h)
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=status,
            native_width=w,
            native_height=h,
            fps_estimate=round(fps, 3),
            dropped_frames=overwritten,
            decode_errors=decode_errors,
            reconnect_count=reconnects,
            last_frame_at=last,
            detail_vi=(
                f"RTSP LIVE trạng thái={status.value}; kích thước DECODED_MEASURED={w}x{h}; "
                f"FPS đo={fps:.2f}; overwritten_latest={overwritten}. "
                "CAMERA_LAB_PASS=false đến khi lab Windows xác nhận. "
                "URI đầy đủ không xuất trong diagnostics."
            ),
            camera_lab_pass=False,
            operationally_ready=ready,
            extras={
                "size_source": "DECODED_MEASURED" if w and h else "UNVERIFIED",
                "cap_prop_hint_wh": list(hint),
                "overwritten_latest": overwritten,
                "decode_errors": decode_errors,
                "clock_trust": ClockTrust.SERVER_RECEIVE.value,
                "diagnostic_uri": "REDACTED",
                "operationally_ready": ready,
            },
        )


# Backward-compatible name used by older imports
def sanitize_rtsp_for_log(uri: str) -> str:
    """Deprecated for exports — strips userinfo but path may still leak. Prefer REDACTED."""
    from urllib.parse import urlparse, urlunparse

    try:
        p = urlparse(uri)
        netloc = p.hostname or ""
        if p.port:
            netloc = f"{netloc}:{p.port}"
        # Intentionally drop path/query for safer logs
        return urlunparse((p.scheme, netloc, "/<redacted>", "", "", ""))
    except Exception:
        return "REDACTED"

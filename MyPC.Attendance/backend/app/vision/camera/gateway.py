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
    frame_id: str
    camera_id: str
    bgr: np.ndarray
    width: int
    height: int
    capture_time_utc: datetime
    receive_time_utc: datetime
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    estimated_skew_ms: float = 0.0
    source_event_id: str = ""
    config_revision: str = ""
    clock_trust: ClockTrust = ClockTrust.SERVER_RECEIVE
    pixel_sha256: str = ""

    def clone_pixels(self) -> np.ndarray:
        """Always return an owned writable copy for consumers."""
        return np.array(self.bgr, copy=True, order="C")


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
    extras: dict[str, Any] = field(default_factory=dict)


def _sha256_pixels(arr: np.ndarray) -> str:
    import hashlib

    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def _seal(arr: np.ndarray) -> np.ndarray:
    """Own + read-only view (consumers must clone_pixels to mutate)."""
    owned = np.array(arr, copy=True, order="C")
    owned.setflags(write=False)
    return owned


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
        sealed = _seal(img)
        now = datetime.now(timezone.utc)
        return CameraFrame(
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            bgr=sealed,
            width=self.width,
            height=self.height,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.MOCK,
            decoder_status=DecoderStatus.OK,
            source_event_id=f"mock-{self._idx}",
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
            pixel_sha256=_sha256_pixels(sealed),
        )

    def health(self) -> GatewayHealth:
        return GatewayHealth(
            provenance=StreamProvenance.MOCK,
            decoder_status=DecoderStatus.OK if self._running else DecoderStatus.OFFLINE,
            native_width=self.width,
            native_height=self.height,
            detail_vi="Chế độ MOCK — không phải camera thật; CAMERA_LAB_PASS=false.",
            camera_lab_pass=False,
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
        sealed = _seal(frame)
        now = datetime.now(timezone.utc)
        h, w = sealed.shape[:2]
        return CameraFrame(
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            bgr=sealed,
            width=w,
            height=h,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
            pixel_sha256=_sha256_pixels(sealed),
        )

    def health(self) -> GatewayHealth:
        ok = self._cap is not None and self._cap.isOpened()
        return GatewayHealth(
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK if ok else DecoderStatus.OFFLINE,
            detail_vi="Video ghi hình được ủy quyền — không phải luồng LIVE.",
            camera_lab_pass=False,
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
            sealed = _seal(frame)
            h, w = sealed.shape[:2]
            self._native = (w, h)  # DECODED_MEASURED
            fr = CameraFrame(
                frame_id=str(uuid.uuid4()),
                camera_id=self.camera_id,
                bgr=sealed,
                width=w,
                height=h,
                capture_time_utc=recv,  # SERVER_RECEIVE — not device PTS
                receive_time_utc=recv,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                source_event_id=str(uuid.uuid4()),
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                pixel_sha256=_sha256_pixels(sealed),
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
            # Return sealed reference; consumers use clone_pixels() to mutate
            if age > self._stale_after:
                return CameraFrame(
                    frame_id=fr.frame_id,
                    camera_id=fr.camera_id,
                    bgr=fr.bgr,
                    width=fr.width,
                    height=fr.height,
                    capture_time_utc=fr.capture_time_utc,
                    receive_time_utc=fr.receive_time_utc,
                    provenance=fr.provenance,
                    decoder_status=DecoderStatus.STALE,
                    estimated_skew_ms=fr.estimated_skew_ms,
                    source_event_id=fr.source_event_id,
                    config_revision=fr.config_revision,
                    clock_trust=fr.clock_trust,
                    pixel_sha256=fr.pixel_sha256,
                )
            return fr

    def health(self) -> GatewayHealth:
        with self._lock:
            last = self._latest.receive_time_utc if self._latest else None
            status = self._status
            overwritten = self._overwritten_latest
            decode_errors = self._decode_errors
            reconnects = self._reconnects
            w, h = self._native
            fps = self._measured_fps()
            hint = self._cap_prop_hint
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
            extras={
                "size_source": "DECODED_MEASURED" if w and h else "UNVERIFIED",
                "cap_prop_hint_wh": list(hint),
                "overwritten_latest": overwritten,
                "decode_errors": decode_errors,
                "clock_trust": ClockTrust.SERVER_RECEIVE.value,
                "diagnostic_uri": "REDACTED",
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

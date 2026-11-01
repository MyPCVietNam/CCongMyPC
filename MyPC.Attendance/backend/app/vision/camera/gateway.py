"""
CameraGateway interfaces for P02.

LiveRTSPGateway uses OpenCV/FFmpeg when an RTSP URI is supplied at runtime.
Credentials must never appear in logs, returned URLs, or diagnostic ZIPs.
CAMERA_LAB_PASS remains BLOCKED until Windows lab evidence exists — successful
TCP/decode in one environment does not imply pilot approval.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

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


@dataclass
class GatewayHealth:
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    native_width: int = 0
    native_height: int = 0
    fps_estimate: float = 0.0
    dropped_frames: int = 0
    stale_frames: int = 0
    reconnect_count: int = 0
    last_frame_at: datetime | None = None
    detail_vi: str = ""
    camera_lab_pass: bool = False  # never set True without Windows lab evidence
    extras: dict[str, Any] = field(default_factory=dict)


def sanitize_rtsp_for_log(uri: str) -> str:
    """Strip userinfo from RTSP URI before any log/diagnostic output."""
    try:
        p = urlparse(uri)
        if p.username or p.password:
            netloc = p.hostname or ""
            if p.port:
                netloc = f"{netloc}:{p.port}"
            p = p._replace(netloc=netloc)
        return urlunparse(p)
    except Exception:
        return "<unparseable-uri>"


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
    """Synthetic frames — never labeled CAMERA_LIVE."""

    def __init__(self, camera_id: str = "mock-0", width: int = 640, height: int = 360) -> None:
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self._running = False
        self._idx = 0

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
        return CameraFrame(
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            bgr=img,
            width=self.width,
            height=self.height,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.MOCK,
            decoder_status=DecoderStatus.OK,
            source_event_id=f"mock-{self._idx}",
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
    """Replay of an authorized local video file for lab — provenance AUTHORIZED_RECORDED."""

    def __init__(self, path: str, camera_id: str = "recorded-0") -> None:
        self.path = path
        self.camera_id = camera_id
        self._cap = None
        self._last: CameraFrame | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        import cv2

        self._cap = cv2.VideoCapture(self.path)
        if not self._cap.isOpened():
            logger.warning("recorded_video_open_failed path_set=%s", bool(self.path))
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
        h, w = frame.shape[:2]
        fr = CameraFrame(
            frame_id=str(uuid.uuid4()),
            camera_id=self.camera_id,
            bgr=frame,
            width=w,
            height=h,
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK,
        )
        with self._lock:
            self._last = fr
        return fr

    def health(self) -> GatewayHealth:
        ok = self._cap is not None and self._cap.isOpened()
        return GatewayHealth(
            provenance=StreamProvenance.AUTHORIZED_RECORDED,
            decoder_status=DecoderStatus.OK if ok else DecoderStatus.OFFLINE,
            detail_vi="Video ghi hình được ủy quyền — không phải luồng LIVE.",
            camera_lab_pass=False,
        )


class LiveRTSPGateway(CameraGateway):
    """
    Live RTSP ingest via OpenCV VideoCapture (FFmpeg backend).

    - Single capture connection; bounded latest-frame buffer (drop stale).
    - Reconnect with exponential backoff + jitter.
    - Never logs credentials; sanitize URI in diagnostics.
    - camera_lab_pass stays False until operator Windows lab sets evidence externally.
    """

    def __init__(
        self,
        rtsp_uri: str,
        camera_id: str = "live-0",
        *,
        max_backoff_s: float = 30.0,
        stale_after_s: float = 3.0,
    ) -> None:
        self._uri = rtsp_uri
        self.camera_id = camera_id
        self._max_backoff = max_backoff_s
        self._stale_after = stale_after_s
        self._cap = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._dropped = 0
        self._reconnects = 0
        self._status = DecoderStatus.NOT_CONFIGURED
        self._native = (0, 0)
        self._fps = 0.0

    def start(self) -> None:
        if not self._uri:
            self._status = DecoderStatus.NOT_CONFIGURED
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"rtsp-{self.camera_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._release()

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _open(self) -> bool:
        import cv2

        # Prefer FFmpeg; do not put password on argv beyond OpenCV's internal handling
        self._cap = cv2.VideoCapture(self._uri, cv2.CAP_FFMPEG)
        ok = bool(self._cap.isOpened())
        if not ok:
            logger.warning(
                "rtsp_open_failed camera_id=%s uri=%s",
                self.camera_id,
                sanitize_rtsp_for_log(self._uri),
            )
            self._release()
            self._status = DecoderStatus.OFFLINE
        else:
            self._status = DecoderStatus.OK
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            self._native = (w, h)
        return ok

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            if self._cap is None and not self._open():
                self._status = DecoderStatus.RECONNECTING
                self._reconnects += 1
                time.sleep(backoff)
                backoff = min(self._max_backoff, backoff * 1.7 + 0.1)
                continue
            backoff = 1.0
            assert self._cap is not None
            ok, frame = self._cap.read()
            recv = datetime.now(timezone.utc)
            if not ok or frame is None:
                self._status = DecoderStatus.RECONNECTING
                self._release()
                continue
            h, w = frame.shape[:2]
            self._native = (w, h)
            fr = CameraFrame(
                frame_id=str(uuid.uuid4()),
                camera_id=self.camera_id,
                bgr=frame,
                width=w,
                height=h,
                capture_time_utc=recv,  # camera PTS trust separate; no fabricated skew claim
                receive_time_utc=recv,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                source_event_id=str(uuid.uuid4()),
            )
            with self._lock:
                if self._latest is not None:
                    self._dropped += 1  # overwrite = drop stale unread
                self._latest = fr
                self._status = DecoderStatus.OK

    def get_latest_frame(self) -> CameraFrame | None:
        with self._lock:
            fr = self._latest
            if fr is None:
                return None
            age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
            if age > self._stale_after:
                self._status = DecoderStatus.STALE
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
                )
            return fr

    def health(self) -> GatewayHealth:
        with self._lock:
            last = self._latest.receive_time_utc if self._latest else None
            status = self._status
            dropped = self._dropped
            reconnects = self._reconnects
            w, h = self._native
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=status,
            native_width=w,
            native_height=h,
            dropped_frames=dropped,
            reconnect_count=reconnects,
            last_frame_at=last,
            detail_vi=(
                f"RTSP gateway trạng thái={status.value}; URI={sanitize_rtsp_for_log(self._uri)}. "
                "CAMERA_LAB_PASS vẫn false cho đến khi lab Windows xác nhận."
            ),
            camera_lab_pass=False,
            extras={"sanitized_uri": sanitize_rtsp_for_log(self._uri)},
        )

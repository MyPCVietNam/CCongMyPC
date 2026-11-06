"""Windows USB UVC LIVE gateway — DirectShow primary, optional MSMF fallback.

Produces CAMERA_LIVE frames (physical USB). Inject ``open_capture`` for CI.
Never forges frames on read failure. Prefer MJPG 1920x1080@30 then 1280x720.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.vision.camera.gateway import (
    CameraFrame,
    CameraGateway,
    ClockTrust,
    DecoderStatus,
    GatewayHealth,
    StreamProvenance,
    frame_looks_corrupt,
)
from app.vision.camera.usb_device import usb_stream_fingerprint

logger = logging.getLogger(__name__)

OpenCaptureFn = Callable[[int, str], Any]  # (index, backend) -> VideoCapture-like

MODE_PREFS: tuple[tuple[str, int, int, float], ...] = (
    ("MJPG", 1920, 1080, 30.0),
    ("MJPG", 1280, 720, 30.0),
    ("", 1920, 1080, 30.0),
    ("", 1280, 720, 30.0),
)


def _default_open_capture(index: int, backend: str):
    import cv2

    api = cv2.CAP_DSHOW if backend == "dshow" else cv2.CAP_MSMF
    return cv2.VideoCapture(int(index), api)


def _fourcc_int(code: str) -> int:
    import cv2

    c = (code or "MJPG")[:4].ljust(4, " ")
    return int(cv2.VideoWriter_fourcc(*c))


def _fourcc_str(val: float | int) -> str:
    try:
        v = int(val)
        return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).strip()
    except Exception:
        return ""


class LiveUsbUvcGateway(CameraGateway):
    """One owned capture loop per USB stable device (lease via stream_fingerprint)."""

    def __init__(
        self,
        *,
        camera_id: str,
        stable_id: str,
        index: int,
        friendly_name: str = "",
        backend: str = "dshow",
        allow_msmf_fallback: bool = True,
        stale_after_s: float = 3.0,
        max_backoff_s: float = 8.0,
        config_revision: str | None = None,
        open_capture: OpenCaptureFn | None = None,
        mode_prefs: tuple[tuple[str, int, int, float], ...] | None = None,
    ) -> None:
        self.camera_id = str(camera_id)
        self.stable_id = stable_id
        self.friendly_name = (friendly_name or "")[:128]
        self._index = int(index)
        self._backend = (backend or "dshow").lower()
        self._allow_msmf = bool(allow_msmf_fallback)
        self._stale_after = float(stale_after_s)
        self._max_backoff = float(max_backoff_s)
        self.config_revision = config_revision or str(uuid.uuid4())
        self.stream_fingerprint = usb_stream_fingerprint(stable_id)
        self._open_capture = open_capture or _default_open_capture
        self._mode_prefs = mode_prefs or MODE_PREFS

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cap = None
        self._latest: CameraFrame | None = None
        self._latest_good: CameraFrame | None = None
        self._status = DecoderStatus.NOT_CONFIGURED
        self._frames_ok = 0
        self._dropped = 0
        self._decode_errors = 0
        self._reconnect_count = 0
        self._native = (0, 0)
        self._fps_est = 0.0
        self._fourcc = ""
        self._requested_mode = ""
        self._transport = "USB_UVC"
        self._detail_vi = ""
        self._last_mono = 0.0
        self._fps_window: list[float] = []

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._status = DecoderStatus.CONNECTING
            self._thread = threading.Thread(
                target=self._loop, name=f"usb-uvc-{self.camera_id}", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=5.0)
        with self._lock:
            self._release_cap_locked()
            self._status = DecoderStatus.STOPPED
            self._thread = None

    def _release_cap_locked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def get_latest_frame(self) -> CameraFrame | None:
        with self._lock:
            fr = self._latest
            if fr is None:
                return None
            age = time.monotonic() - float(fr.receive_monotonic or 0.0)
            if self._status in {
                DecoderStatus.RECONNECTING,
                DecoderStatus.CONNECTING,
                DecoderStatus.OFFLINE,
            }:
                return fr.with_status(DecoderStatus.STALE)
            if age > self._stale_after:
                return fr.with_status(DecoderStatus.STALE)
            return fr

    def get_latest_good_frame(self) -> CameraFrame | None:
        with self._lock:
            if self._status != DecoderStatus.OK:
                return None
            return self._latest_good

    def health(self) -> GatewayHealth:
        with self._lock:
            age_ms = None
            if self._latest is not None and self._latest.receive_monotonic:
                age_ms = int((time.monotonic() - self._latest.receive_monotonic) * 1000)
            ready = (
                self._status == DecoderStatus.OK
                and self._frames_ok > 0
                and self._native[0] > 0
                and self._native[1] > 0
            )
            return GatewayHealth(
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=self._status,
                native_width=int(self._native[0]),
                native_height=int(self._native[1]),
                fps_estimate=float(self._fps_est),
                dropped_frames=int(self._dropped),
                decode_errors=int(self._decode_errors),
                reconnect_count=int(self._reconnect_count),
                last_frame_at=self._latest.receive_time_utc if self._latest else None,
                detail_vi=self._detail_vi or "USB UVC",
                camera_lab_pass=False,
                operationally_ready=bool(ready),
                extras={
                    "transport": self._transport,
                    "source_type": "USB_UVC",
                    "live_decoded": bool(ready),
                    "connection_status": (
                        "USB_CONNECTED"
                        if ready
                        else (
                            "USB_DISCONNECTED"
                            if self._status
                            in {
                                DecoderStatus.OFFLINE,
                                DecoderStatus.RECONNECTING,
                                DecoderStatus.STOPPED,
                            }
                            else "USB_BUSY"
                            if self._status
                            in {DecoderStatus.CONNECTING, DecoderStatus.DEGRADED}
                            else self._status.value
                        )
                    ),
                    "source_fps_status": "MEASURED" if self._fps_est > 0 else "UNKNOWN_INSUFFICIENT_SAMPLES",
                    "source_fps_measured": float(self._fps_est),
                    "stable_id_short": (self.stable_id[:12] + "…") if len(self.stable_id) > 12 else self.stable_id,
                    "friendly_name": self.friendly_name,
                    "fourcc": self._fourcc,
                    "requested_mode": self._requested_mode,
                    "actual_width": int(self._native[0]),
                    "actual_height": int(self._native[1]),
                    "frame_age_ms": age_ms,
                    "backend": self._backend,
                    "config_revision": self.config_revision,
                    "stream_fingerprint": self.stream_fingerprint,
                    "index_hint_not_identity": True,
                    "frames_ok": int(self._frames_ok),
                },
            )

    def _negotiate(self, cap) -> None:
        import cv2

        for fourcc, w, h, fps in self._mode_prefs:
            try:
                if fourcc:
                    cap.set(cv2.CAP_PROP_FOURCC, _fourcc_int(fourcc))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(w))
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(h))
                cap.set(cv2.CAP_PROP_FPS, float(fps))
                self._requested_mode = f"{fourcc or 'DEFAULT'} {w}x{h}@{fps}"
                # Verify actual — never trust set() alone
                aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                af = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                fc = _fourcc_str(cap.get(cv2.CAP_PROP_FOURCC) or 0)
                if aw >= 640 and ah >= 480:
                    self._native = (aw, ah)
                    self._fourcc = fc
                    self._detail_vi = (
                        f"USB UVC thực tế {aw}x{ah} fourcc={fc or '?'} "
                        f"(yêu cầu {self._requested_mode}; FPS device-report={af})"
                    )
                    return
            except Exception:
                continue
        # Last resort: accept whatever is open
        try:
            aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            self._native = (aw, ah)
            self._fourcc = _fourcc_str(cap.get(cv2.CAP_PROP_FOURCC) or 0)
            self._detail_vi = f"USB UVC mở được nhưng chế độ thấp/không xác nhận: {aw}x{ah}"
        except Exception:
            self._detail_vi = "USB UVC mở nhưng không đọc được thuộc tính khung."

    def _open(self):
        backends = [self._backend]
        if self._allow_msmf and "msmf" not in backends:
            backends.append("msmf")
        last_err = ""
        for be in backends:
            try:
                cap = self._open_capture(self._index, be)
                if cap is not None and getattr(cap, "isOpened", lambda: False)():
                    self._backend = be
                    self._negotiate(cap)
                    return cap
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                last_err = f"open_failed:{be}"
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}:{be}"
        raise RuntimeError(last_err or "USB_OPEN_FAILED")

    def _publish(self, fr: CameraFrame, *, good: bool) -> None:
        with self._lock:
            self._latest = fr
            self._last_mono = time.monotonic()
            if good:
                self._latest_good = fr
                self._frames_ok += 1
                self._status = DecoderStatus.OK
            now = time.monotonic()
            self._fps_window = [t for t in self._fps_window if now - t < 2.0]
            self._fps_window.append(now)
            if len(self._fps_window) >= 2:
                dt = self._fps_window[-1] - self._fps_window[0]
                if dt > 0:
                    self._fps_est = (len(self._fps_window) - 1) / dt

    def _reresolve_index(self) -> None:
        """On reconnect, re-match the same stable_id; fail closed on identity mismatch."""
        from app.vision.camera.usb_device import resolve_device

        try:
            dev = resolve_device(stable_id=self.stable_id)
        except ValueError as exc:
            with self._lock:
                self._status = DecoderStatus.OFFLINE
                self._detail_vi = (
                    f"USB định danh không khớp sau cắm lại ({exc}) — "
                    "không tự chuyển sang webcam khác."
                )
                self._latest_good = None
            raise
        if dev.index_hint is not None:
            self._index = int(dev.index_hint)
        if dev.friendly_name:
            self.friendly_name = dev.friendly_name[:128]

    def _loop(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._status = DecoderStatus.CONNECTING
                    self._detail_vi = "Đang mở USB UVC…"
                # Always re-resolve stable identity before open (index may reorder)
                if self._open_capture is _default_open_capture:
                    self._reresolve_index()
                cap = self._open()
                with self._lock:
                    self._cap = cap
                    self._status = DecoderStatus.OK
                    backoff = 0.5
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        with self._lock:
                            self._decode_errors += 1
                            self._dropped += 1
                            self._status = DecoderStatus.DEGRADED
                            self._detail_vi = "USB đọc khung thất bại — không tạo khung giả."
                            self._latest_good = None
                        break
                    if frame_looks_corrupt(frame):
                        with self._lock:
                            self._decode_errors += 1
                            self._status = DecoderStatus.DEGRADED
                            self._latest_good = None
                        continue
                    now = datetime.now(timezone.utc)
                    h, w = frame.shape[:2]
                    with self._lock:
                        self._native = (int(w), int(h))
                    fr = CameraFrame.from_bgr(
                        frame,
                        frame_id=str(uuid.uuid4()),
                        camera_id=self.camera_id,
                        capture_time_utc=now,
                        receive_time_utc=now,
                        provenance=StreamProvenance.CAMERA_LIVE,
                        decoder_status=DecoderStatus.OK,
                        config_revision=self.config_revision,
                        clock_trust=ClockTrust.SERVER_RECEIVE,
                        integrity_ok=True,
                    )
                    self._publish(fr, good=True)
                    time.sleep(0.001)
                with self._lock:
                    self._release_cap_locked()
                    self._reconnect_count += 1
                    self._status = DecoderStatus.RECONNECTING
                    self._detail_vi = "USB mất khung / ngắt — đang thử kết nối lại."
                    self._latest_good = None
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._release_cap_locked()
                    self._reconnect_count += 1
                    self._status = DecoderStatus.OFFLINE
                    if "USB định danh" not in (self._detail_vi or ""):
                        self._detail_vi = f"USB UVC lỗi: {type(exc).__name__}"
                    self._latest_good = None
                logger.info("usb_uvc_reconnect camera=%s err=%s", self.camera_id, type(exc).__name__)
            if self._stop.is_set():
                break
            time.sleep(min(backoff, self._max_backoff))
            backoff = min(backoff * 1.5, self._max_backoff)


def diagnose_usb_modes(
    *,
    index: int,
    backend: str = "dshow",
    open_capture: OpenCaptureFn | None = None,
    mode_prefs: tuple[tuple[str, int, int, float], ...] | None = None,
) -> list[dict[str, Any]]:
    """Owner diagnostic: try modes and report *actual* WxH/FOURCC (not requested)."""
    open_fn = open_capture or _default_open_capture
    prefs = mode_prefs or MODE_PREFS
    results: list[dict[str, Any]] = []
    for fourcc, w, h, fps in prefs:
        cap = None
        try:
            cap = open_fn(int(index), backend)
            if cap is None or not getattr(cap, "isOpened", lambda: False)():
                results.append(
                    {
                        "requested": f"{fourcc or 'DEFAULT'} {w}x{h}@{fps}",
                        "opened": False,
                        "actual_width": 0,
                        "actual_height": 0,
                        "actual_fourcc": "",
                        "note_vi": "Không mở được thiết bị ở chế độ này.",
                    }
                )
                continue
            import cv2

            if fourcc:
                cap.set(cv2.CAP_PROP_FOURCC, _fourcc_int(fourcc))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(w))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(h))
            cap.set(cv2.CAP_PROP_FPS, float(fps))
            ok, frame = cap.read()
            aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if ok and frame is not None:
                ah2, aw2 = frame.shape[:2]
                aw, ah = int(aw2), int(ah2)
            results.append(
                {
                    "requested": f"{fourcc or 'DEFAULT'} {w}x{h}@{fps}",
                    "opened": True,
                    "frame_ok": bool(ok and frame is not None),
                    "actual_width": aw,
                    "actual_height": ah,
                    "actual_fourcc": _fourcc_str(cap.get(cv2.CAP_PROP_FOURCC) or 0),
                    "device_reported_fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
                    "note_vi": (
                        "Đây là kích thước đo được — không phải giá trị set() yêu cầu."
                    ),
                    "claims_4k": False,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "requested": f"{fourcc or 'DEFAULT'} {w}x{h}@{fps}",
                    "opened": False,
                    "error": type(exc).__name__,
                    "note_vi": "Lỗi khi thử chế độ.",
                }
            )
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return results

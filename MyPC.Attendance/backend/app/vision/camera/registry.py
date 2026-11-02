"""Per-camera LIVE/REPLAY/MOCK gateway registry — single source of truth for preview/enroll/ingest."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.vision.camera.gateway import (
    CameraFrame,
    CameraGateway,
    DecoderStatus,
    GatewayHealth,
    StreamProvenance,
)


class FrameAccessError(RuntimeError):
    def __init__(self, code: str, message_vi: str) -> None:
        super().__init__(message_vi)
        self.code = code
        self.message_vi = message_vi


@dataclass
class BoundSource:
    camera_db_id: int
    gateway: CameraGateway
    config_revision: str
    provenance: StreamProvenance
    profile: str = "MAIN"


class CameraSourceRegistry:
    """Maps camera DB id → active gateway. Preview/enrollment/attendance must use this."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[int, BoundSource] = {}
        self.default_gateway: CameraGateway | None = None

    def bind(
        self,
        camera_db_id: int,
        gateway: CameraGateway,
        *,
        provenance: StreamProvenance,
        profile: str = "MAIN",
    ) -> BoundSource:
        with self._lock:
            old = self._by_id.get(camera_db_id)
            if old is not None:
                try:
                    old.gateway.stop()
                except Exception:
                    pass
            rev = str(uuid.uuid4())
            if hasattr(gateway, "config_revision"):
                gateway.config_revision = rev
            if hasattr(gateway, "_latest"):
                lock = getattr(gateway, "_lock", None)
                if lock is not None:
                    with lock:
                        gateway._latest = None  # type: ignore[attr-defined]
                else:
                    try:
                        gateway._latest = None  # type: ignore[attr-defined]
                    except Exception:
                        pass
            bound = BoundSource(
                camera_db_id=camera_db_id,
                gateway=gateway,
                config_revision=rev,
                provenance=provenance,
                profile=profile,
            )
            self._by_id[camera_db_id] = bound
            self.default_gateway = gateway
            return bound

    def unbind(self, camera_db_id: int) -> None:
        with self._lock:
            old = self._by_id.pop(camera_db_id, None)
            if old is not None:
                try:
                    old.gateway.stop()
                except Exception:
                    pass
            if old is not None and self.default_gateway is old.gateway:
                nxt = next(iter(self._by_id.values()), None)
                self.default_gateway = nxt.gateway if nxt is not None else None

    def get(self, camera_db_id: int) -> BoundSource | None:
        with self._lock:
            return self._by_id.get(camera_db_id)

    def get_frame(
        self,
        camera_db_id: int,
        *,
        expected_revision: str | None = None,
        allow_mock: bool = False,
        allow_recorded: bool = False,
        require_live: bool = False,
        allow_stale: bool = False,
        max_age_s: float = 3.0,
        expected_profile: str | None = None,
        for_biometric: bool = False,
    ) -> tuple[BoundSource, CameraFrame]:
        """
        Unified frame access. Biometric paths: require_live + for_biometric + not allow_stale.
        Fail closed on any mismatch — never `pass`.
        """
        bound = self.get(camera_db_id)
        if bound is None:
            raise FrameAccessError("CAMERA_SOURCE_UNBOUND", "Chưa gắn nguồn camera.")
        if expected_revision and expected_revision != bound.config_revision:
            raise FrameAccessError("CAMERA_CONFIG_REVISION_MISMATCH", "Cấu hình camera đã đổi.")
        if expected_profile and expected_profile != bound.profile:
            raise FrameAccessError("CAMERA_PROFILE_MISMATCH", "Sai profile luồng camera.")
        if require_live and bound.provenance != StreamProvenance.CAMERA_LIVE:
            raise FrameAccessError("LIVE_REQUIRED", "Yêu cầu nguồn CAMERA_LIVE.")
        if bound.provenance == StreamProvenance.MOCK and not allow_mock:
            raise FrameAccessError("MOCK_NOT_ALLOWED", "MOCK không được phép trên đường đi này.")
        if bound.provenance == StreamProvenance.AUTHORIZED_RECORDED and not (
            allow_recorded or allow_mock
        ):
            raise FrameAccessError("RECORDED_NOT_ALLOWED", "REPLAY không được phép trên đường đi này.")
        if for_biometric and bound.provenance != StreamProvenance.CAMERA_LIVE:
            raise FrameAccessError(
                "BIOMETRIC_REQUIRES_LIVE",
                "Nhận diện/ghi công chính thức chỉ chấp nhận CAMERA_LIVE đã xác minh.",
            )

        fr = bound.gateway.get_latest_frame()
        if fr is None:
            raise FrameAccessError("NO_FRAME", "Chưa có khung hình đã giải mã.")
        if not fr._pixels or fr.width <= 0 or fr.height <= 0:
            raise FrameAccessError("EMPTY_FRAME", "Khung hình trống hoặc kích thước không hợp lệ.")
        # camera_id on frame must match DB id string we bound
        if str(fr.camera_id) not in {str(camera_db_id), str(bound.camera_db_id)}:
            raise FrameAccessError(
                "CROSS_CAMERA_REJECTED",
                "Khung hình không thuộc camera_id đang yêu cầu.",
            )
        if fr.config_revision and fr.config_revision != bound.config_revision:
            raise FrameAccessError("STALE_FRAME_REVISION", "Khung hình cũ sau đổi cấu hình.")
        if fr.provenance != bound.provenance:
            raise FrameAccessError("PROVENANCE_MISMATCH", "Provenance khung hình không khớp nguồn gắn.")
        if fr.decoder_status == DecoderStatus.STALE and (for_biometric or not allow_stale):
            raise FrameAccessError("STALE_FRAME", "Khung hình quá hạn — không dùng cho nhận diện.")
        if fr.decoder_status not in {DecoderStatus.OK, DecoderStatus.STALE}:
            raise FrameAccessError("DECODER_NOT_OK", f"Decoder={fr.decoder_status.value}.")

        age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
        if age < 0:
            raise FrameAccessError("CLOCK_ANOMALY", "Thời gian nhận khung hình bất thường.")
        if age > max_age_s and (for_biometric or not allow_stale):
            raise FrameAccessError("FRAME_TOO_OLD", f"Tuổi khung hình {age:.2f}s vượt ngưỡng.")
        if for_biometric and fr.clock_trust.value not in {"SERVER_RECEIVE"}:
            raise FrameAccessError("UNTRUSTED_CLOCK", "Đồng hồ khung hình chưa tin cậy cho chấm công.")
        return bound, fr

    def health(self, camera_db_id: int | None = None) -> dict[str, Any]:
        with self._lock:
            if camera_db_id is None:
                items = list(self._by_id.items())
            else:
                b = self._by_id.get(camera_db_id)
                items = [(camera_db_id, b)] if b else []
        out = []
        for cid, b in items:
            if b is None:
                continue
            h: GatewayHealth = b.gateway.health()
            # Display may show STALE; operational readiness is stricter
            op_ready = bool(getattr(h, "operationally_ready", False)) and h.decoder_status.value == "OK"
            out.append(
                {
                    "camera_id": cid,
                    "config_revision": b.config_revision,
                    "profile": b.profile,
                    "provenance": b.provenance.value,
                    "decoder_status": h.decoder_status.value,
                    "native_width": h.native_width,
                    "native_height": h.native_height,
                    "fps_measured": h.fps_estimate,
                    "overwritten_latest": h.dropped_frames,
                    "reconnect_count": h.reconnect_count,
                    "operationally_ready": op_ready,
                    "camera_lab_pass": False,
                    "detail_vi": h.detail_vi,
                }
            )
        any_ready = any(s.get("operationally_ready") for s in out)
        return {"sources": out, "camera_lab_pass": False, "ready": any_ready}

    def shutdown_all(self) -> None:
        with self._lock:
            ids = list(self._by_id.keys())
        for cid in ids:
            self.unbind(cid)

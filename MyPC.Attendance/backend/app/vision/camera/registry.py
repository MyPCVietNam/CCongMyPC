"""Per-camera LIVE/REPLAY/MOCK gateway registry — single decode pipeline per physical stream."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.vision.camera.gateway import (
    CameraFrame,
    CameraGateway,
    DecoderStatus,
    GatewayHealth,
    LiveRTSPGateway,
    StreamProvenance,
    physical_stream_fingerprint,
)
from app.vision.camera.usb_uvc_gateway import LiveUsbUvcGateway


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
    stream_fingerprint: str = ""


@dataclass
class _StreamLease:
    fingerprint: str
    gateway: CameraGateway
    holders: set[int] = field(default_factory=set)
    config_revision: str = ""


def _is_leaseable_live(gateway: CameraGateway) -> bool:
    return isinstance(gateway, (LiveRTSPGateway, LiveUsbUvcGateway))


class CameraSourceRegistry:
    """Maps camera DB id → active gateway. One LIVE decode loop per physical stream/device."""

    def __init__(self) -> None:
        self._last_biometric_frame_ids: dict[int, str] = {}
        self._lock = threading.RLock()
        self._by_id: dict[int, BoundSource] = {}
        self._leases: dict[str, _StreamLease] = {}
        self.default_gateway: CameraGateway | None = None

    def bind(
        self,
        camera_db_id: int,
        gateway: CameraGateway,
        *,
        provenance: StreamProvenance,
        profile: str = "MAIN",
        stream_fingerprint: str | None = None,
        preferred_revision: str | None = None,
    ) -> BoundSource:
        """Bind gateway. ``preferred_revision`` preserves trust subject on same-device USB rebind.

        RTSP callers should omit preferred_revision (always rotate on fresh lease) unless they
        intentionally pass a revision. USB same-identity rebind passes the persisted revision.
        """
        with self._lock:
            # Capture prior lease revision for this fingerprint before unbind (same-device rebind)
            prior_fp = stream_fingerprint or ""
            if isinstance(gateway, LiveUsbUvcGateway):
                prior_fp = prior_fp or gateway.stream_fingerprint
            elif isinstance(gateway, LiveRTSPGateway):
                prior_fp = prior_fp or gateway.stream_fingerprint or physical_stream_fingerprint(
                    gateway._uri
                )
            prior_lease_rev = ""
            if prior_fp and prior_fp in self._leases:
                prior_lease_rev = self._leases[prior_fp].config_revision or ""

            # Drop previous binding for this camera id
            self._unbind_locked(camera_db_id, stop_if_unshared=True)

            fp = stream_fingerprint or ""
            if isinstance(gateway, LiveRTSPGateway):
                fp = fp or gateway.stream_fingerprint or physical_stream_fingerprint(gateway._uri)
            elif isinstance(gateway, LiveUsbUvcGateway):
                fp = fp or gateway.stream_fingerprint

            def _pick_rev(*candidates: str | None) -> str:
                for c in candidates:
                    if c and str(c).strip():
                        return str(c).strip()
                return str(uuid.uuid4())

            if _is_leaseable_live(gateway) and fp:
                # Reuse existing decode/capture pipeline for same physical stream/device
                lease = self._leases.get(fp)
                if lease is not None and lease.gateway is not gateway:
                    try:
                        gateway.stop()
                    except Exception:
                        pass
                    gateway = lease.gateway
                    # Retarget displayed camera_id on shared gateway for frame stamps
                    gateway.camera_id = str(camera_db_id)
                    lease.holders.add(camera_db_id)
                    rev = _pick_rev(lease.config_revision, preferred_revision, prior_lease_rev)
                    lease.config_revision = rev
                else:
                    # Fresh lease: preserve preferred/prior for USB same-identity; else rotate
                    if isinstance(gateway, LiveUsbUvcGateway):
                        rev = _pick_rev(preferred_revision, prior_lease_rev)
                    else:
                        rev = _pick_rev(None)  # RTSP: always new UUID on fresh lease
                    if hasattr(gateway, "config_revision"):
                        gateway.config_revision = rev
                    self._leases[fp] = _StreamLease(
                        fingerprint=fp,
                        gateway=gateway,
                        holders={camera_db_id},
                        config_revision=rev,
                    )
            else:
                rev = _pick_rev(
                    preferred_revision if isinstance(gateway, LiveUsbUvcGateway) else None
                )
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

            if hasattr(gateway, "config_revision"):
                gateway.config_revision = rev

            bound = BoundSource(
                camera_db_id=camera_db_id,
                gateway=gateway,
                config_revision=rev,
                provenance=provenance,
                profile=profile,
                stream_fingerprint=fp,
            )
            self._by_id[camera_db_id] = bound
            self.default_gateway = gateway
            return bound

    def _unbind_locked(self, camera_db_id: int, *, stop_if_unshared: bool) -> None:
        old = self._by_id.pop(camera_db_id, None)
        if old is None:
            return
        fp = old.stream_fingerprint
        if fp and fp in self._leases and _is_leaseable_live(old.gateway):
            lease = self._leases[fp]
            lease.holders.discard(camera_db_id)
            if stop_if_unshared and not lease.holders:
                try:
                    lease.gateway.stop()
                except Exception:
                    pass
                self._leases.pop(fp, None)
        else:
            if stop_if_unshared:
                try:
                    old.gateway.stop()
                except Exception:
                    pass
        if self.default_gateway is old.gateway:
            nxt = next(iter(self._by_id.values()), None)
            self.default_gateway = nxt.gateway if nxt is not None else None

    def unbind(self, camera_db_id: int) -> None:
        with self._lock:
            self._unbind_locked(camera_db_id, stop_if_unshared=True)

    def get(self, camera_db_id: int) -> BoundSource | None:
        with self._lock:
            return self._by_id.get(camera_db_id)

    def lease_holders(self, fingerprint: str) -> list[int]:
        with self._lock:
            lease = self._leases.get(fingerprint)
            return sorted(lease.holders) if lease else []

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
        require_integrity: bool | None = None,
    ) -> tuple[BoundSource, CameraFrame]:
        """
        Unified frame access. Biometric paths: require_live + for_biometric + not allow_stale
        + integrity_ok. Fail closed on any mismatch — never `pass`.
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

        # Biometric paths ALWAYS require integrity — callers cannot bypass via require_integrity=False
        want_integrity = True if for_biometric else (
            True if require_integrity is None else bool(require_integrity)
        )

        # Live decoder health gate: never reuse a prior good frame while unhealthy
        if for_biometric and hasattr(bound.gateway, "health"):
            gh = bound.gateway.health()
            st = gh.decoder_status
            if st in {
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
                raise FrameAccessError(
                    "DECODER_UNHEALTHY",
                    f"Decoder={st.value} — không tái sử dụng khung tốt cũ cho chấm công.",
                )
            if not getattr(gh, "operationally_ready", False):
                raise FrameAccessError(
                    "DECODER_NOT_READY",
                    "Decoder chưa operationally_ready — từ chối quan sát sinh trắc.",
                )

        if want_integrity and hasattr(bound.gateway, "get_latest_good_frame"):
            fr = bound.gateway.get_latest_good_frame()  # type: ignore[attr-defined]
        else:
            fr = bound.gateway.get_latest_frame()
        if fr is None:
            raise FrameAccessError("NO_FRAME", "Chưa có khung hình đã giải mã.")
        if not fr._pixels or fr.width <= 0 or fr.height <= 0:
            raise FrameAccessError("EMPTY_FRAME", "Khung hình trống hoặc kích thước không hợp lệ.")
        if want_integrity and not getattr(fr, "integrity_ok", True):
            raise FrameAccessError(
                "CORRUPT_FRAME",
                "Khung hình hỏng/thiếu reference HEVC — không dùng cho nhận diện hoặc bằng chứng.",
            )
        allowed_ids = {str(camera_db_id), str(bound.camera_db_id)}
        if bound.stream_fingerprint:
            allowed_ids.update(str(x) for x in self.lease_holders(bound.stream_fingerprint))
        if str(fr.camera_id) not in allowed_ids:
            raise FrameAccessError(
                "CROSS_CAMERA_REJECTED",
                "Khung hình không thuộc camera_id đang yêu cầu.",
            )
        if fr.config_revision and fr.config_revision != bound.config_revision:
            raise FrameAccessError("STALE_FRAME_REVISION", "Khung hình cũ sau đổi cấu hình.")
        if fr.provenance != bound.provenance:
            raise FrameAccessError("PROVENANCE_MISMATCH", "Provenance khung hình không khớp nguồn gắn.")
        if for_biometric and fr.provenance != StreamProvenance.CAMERA_LIVE:
            raise FrameAccessError("BIOMETRIC_REQUIRES_LIVE", "Sinh trắc yêu cầu CAMERA_LIVE.")
        if fr.decoder_status == DecoderStatus.STALE and (for_biometric or not allow_stale):
            raise FrameAccessError("STALE_FRAME", "Khung hình quá hạn — không dùng cho nhận diện.")
        if fr.decoder_status == DecoderStatus.DEGRADED and (for_biometric or want_integrity):
            raise FrameAccessError("DEGRADED_FRAME", "Luồng đang DEGRADED — không dùng cho nhận diện.")
        if for_biometric and fr.decoder_status != DecoderStatus.OK:
            raise FrameAccessError("DECODER_NOT_OK", f"Decoder={fr.decoder_status.value}.")
        if fr.decoder_status not in {
            DecoderStatus.OK,
            DecoderStatus.STALE,
            DecoderStatus.DEGRADED,
        }:
            raise FrameAccessError("DECODER_NOT_OK", f"Decoder={fr.decoder_status.value}.")

        age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
        if age < 0:
            raise FrameAccessError("CLOCK_ANOMALY", "Thời gian nhận khung hình bất thường.")
        if age > max_age_s and (for_biometric or not allow_stale):
            raise FrameAccessError("FRAME_TOO_OLD", f"Tuổi khung hình {age:.2f}s vượt ngưỡng.")
        if for_biometric and fr.clock_trust.value not in {"SERVER_RECEIVE"}:
            raise FrameAccessError("UNTRUSTED_CLOCK", "Đồng hồ khung hình chưa tin cậy cho chấm công.")

        # Reject repeated frame_id for biometric — atomic under registry lock (P1-06).
        # Durable exactly-once for attendance side-effects remains RawObservation.idempotency_key.
        if for_biometric:
            with self._lock:
                prev = self._last_biometric_frame_ids.get(camera_db_id)
                if prev and prev == fr.frame_id:
                    raise FrameAccessError(
                        "DUPLICATE_FRAME_ID",
                        "frame_id trùng lần quan sát trước — từ chối tái sử dụng.",
                    )
                self._last_biometric_frame_ids[camera_db_id] = fr.frame_id
        return bound, fr

    def health(self, camera_db_id: int | None = None) -> dict[str, Any]:
        with self._lock:
            if camera_db_id is None:
                items = list(self._by_id.items())
            else:
                b = self._by_id.get(camera_db_id)
                items = [(camera_db_id, b)] if b else []
            leases = {
                fp: sorted(lease.holders) for fp, lease in self._leases.items()
            }
        out = []
        for cid, b in items:
            if b is None:
                continue
            h: GatewayHealth = b.gateway.health()
            op_ready = bool(getattr(h, "operationally_ready", False)) and h.decoder_status.value == "OK"
            extras = dict(h.extras or {})
            out.append(
                {
                    "camera_id": cid,
                    "config_revision": b.config_revision,
                    "profile": b.profile,
                    "provenance": b.provenance.value,
                    "stream_fingerprint": b.stream_fingerprint,
                    "decoder_status": h.decoder_status.value,
                    "native_width": h.native_width,
                    "native_height": h.native_height,
                    "fps_measured": h.fps_estimate,
                    "fps_estimate": h.fps_estimate,
                    "overwritten_latest": h.dropped_frames,
                    "reconnect_count": h.reconnect_count,
                    "corrupt_frames": extras.get("corrupt_frames", 0),
                    "hevc_ref_events": extras.get("hevc_ref_events", 0),
                    "live_decoded": bool(extras.get("live_decoded")),
                    "connection_status": extras.get("connection_status"),
                    "source_fps_status": extras.get("source_fps_status"),
                    "source_fps_measured": extras.get("source_fps_measured"),
                    "frame_age_ms": extras.get("frame_age_ms"),
                    "native_decoder_error_category": extras.get(
                        "native_decoder_error_category", "UNAVAILABLE"
                    ),
                    "operationally_ready": op_ready,
                    "camera_lab_pass": False,
                    "detail_vi": h.detail_vi,
                    "extras": extras,
                }
            )
        any_ready = any(s.get("operationally_ready") for s in out)
        return {
            "sources": out,
            "camera_lab_pass": False,
            "ready": any_ready,
            "physical_stream_leases": leases,
        }

    def shutdown_all(self) -> None:
        with self._lock:
            ids = list(self._by_id.keys())
        for cid in ids:
            self.unbind(cid)

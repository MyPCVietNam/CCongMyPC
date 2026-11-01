"""Per-camera LIVE/REPLAY/MOCK gateway registry — single source of truth for preview/enroll/ingest."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any

from app.vision.camera.gateway import CameraFrame, CameraGateway, GatewayHealth, StreamProvenance


@dataclass
class BoundSource:
    camera_db_id: int
    gateway: CameraGateway
    config_revision: str
    provenance: StreamProvenance
    profile: str = "MAIN"


class CameraSourceRegistry:
    """Maps camera DB id → active gateway. Preview/enrollment must use this, not a parallel path."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[int, BoundSource] = {}
        # Legacy singleton pointer for older health endpoint
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
            # Single source of truth: frames must carry the same revision as BoundSource
            if hasattr(gateway, "config_revision"):
                gateway.config_revision = rev
            # Drop any pre-bind latest so revision/camera cannot leak across reconfigs
            latest = getattr(gateway, "_latest", None)
            lock = getattr(gateway, "_lock", None)
            if latest is not None or hasattr(gateway, "_latest"):
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
    ) -> tuple[BoundSource, CameraFrame]:
        bound = self.get(camera_db_id)
        if bound is None:
            raise LookupError("CAMERA_SOURCE_UNBOUND")
        if expected_revision and expected_revision != bound.config_revision:
            raise RuntimeError("CAMERA_CONFIG_REVISION_MISMATCH")
        if bound.provenance == StreamProvenance.MOCK and not allow_mock:
            raise RuntimeError("MOCK_NOT_ALLOWED_FOR_LIVE_PATH")
        fr = bound.gateway.get_latest_frame()
        if fr is None:
            raise LookupError("NO_FRAME")
        if fr.camera_id and str(fr.camera_id) not in {str(camera_db_id), bound.gateway.__class__.__name__}:
            # Soft check — LiveRTSP uses string camera_id we set
            pass
        if fr.config_revision and fr.config_revision != bound.config_revision:
            raise RuntimeError("STALE_FRAME_REVISION")
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
                    "camera_lab_pass": False,
                    "detail_vi": h.detail_vi,
                }
            )
        return {"sources": out, "camera_lab_pass": False}

    def shutdown_all(self) -> None:
        with self._lock:
            ids = list(self._by_id.keys())
        for cid in ids:
            self.unbind(cid)

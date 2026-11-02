"""NativeDecodedFrame contract — untouched decoded BGR (not sensor RAW)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.vision.camera.gateway import ClockTrust, DecoderStatus, StreamProvenance


@dataclass(frozen=True)
class NativeDecodedFrame:
    frame_id: str
    camera_id: str
    profile: str
    config_revision: str
    provenance: StreamProvenance
    decoder_status: DecoderStatus
    clock_trust: ClockTrust
    receive_time_utc: datetime
    receive_monotonic: float
    native_width: int
    native_height: int
    processing_model_hash: str
    pixel_sha256: str
    _bgr_ro: np.ndarray

    @classmethod
    def from_camera_frame(
        cls,
        fr,
        *,
        profile: str = "MAIN",
        receive_monotonic: float,
        processing_model_hash: str = "",
        require_ok: bool = True,
    ) -> "NativeDecodedFrame":
        """Seal a biometric/recognition frame. Rejects DEGRADED/STALE/corrupt when require_ok."""
        if require_ok:
            status = getattr(fr, "decoder_status", None)
            if status not in {DecoderStatus.OK, None}:
                raise ValueError(
                    f"NativeDecodedFrame rejects decoder_status={getattr(status, 'value', status)}"
                )
            if hasattr(fr, "integrity_ok") and not bool(fr.integrity_ok):
                raise ValueError("NativeDecodedFrame rejects integrity_ok=False (corrupt/HEVC)")
        owned = np.array(fr.bgr, copy=True, order="C")
        owned.setflags(write=False)
        digest = hashlib.sha256(np.ascontiguousarray(owned).tobytes()).hexdigest()
        return cls(
            frame_id=fr.frame_id,
            camera_id=str(fr.camera_id),
            profile=profile,
            config_revision=fr.config_revision,
            provenance=fr.provenance,
            decoder_status=fr.decoder_status,
            clock_trust=fr.clock_trust,
            receive_time_utc=fr.receive_time_utc,
            receive_monotonic=receive_monotonic,
            native_width=fr.width,
            native_height=fr.height,
            processing_model_hash=processing_model_hash,
            pixel_sha256=digest,
            _bgr_ro=owned,
        )

    def clone_pixels(self) -> np.ndarray:
        return np.array(self._bgr_ro, copy=True, order="C")

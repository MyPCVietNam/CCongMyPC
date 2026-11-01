"""Sanitize optional ffprobe JSON — strip secret-bearing / unknown keys."""

from __future__ import annotations

from typing import Any

ALLOWED_TOP = {"streams", "format"}
ALLOWED_STREAM = {
    "index",
    "codec_name",
    "codec_type",
    "width",
    "height",
    "pix_fmt",
    "avg_frame_rate",
    "r_frame_rate",
    "profile",
    "level",
}
ALLOWED_FORMAT = {"format_name", "duration", "nb_streams", "bit_rate"}
FORBIDDEN_SUBSTR = (
    "filename",
    "url",
    "uri",
    "rtsp",
    "user",
    "pass",
    "token",
    "auth",
    "secret",
    "cookie",
)


def _key_forbidden(key: str) -> bool:
    low = key.lower()
    return any(s in low for s in FORBIDDEN_SUBSTR)


def sanitize_ffprobe(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "UNVERIFIED", "note_vi": "Không có metadata ffprobe."}
    out: dict[str, Any] = {"status": "SANITIZED"}
    streams_in = payload.get("streams")
    if isinstance(streams_in, list):
        clean_streams = []
        for s in streams_in:
            if not isinstance(s, dict):
                continue
            clean_streams.append({k: s[k] for k in ALLOWED_STREAM if k in s and not _key_forbidden(k)})
        out["streams"] = clean_streams
    fmt = payload.get("format")
    if isinstance(fmt, dict):
        out["format"] = {k: fmt[k] for k in ALLOWED_FORMAT if k in fmt and not _key_forbidden(k)}
    return out

"""PR16-HF1: frontend diag lane retain contract (mirrored from diagLanes.ts)."""

from __future__ import annotations


def retain_both(handshake, legacy):
    return {"handshake": handshake, "legacy": legacy}


def ui_state(cam, preview, live):
    decoder = (live or {}).get("decoder_status") or (preview or {}).get("decoder_status") or (
        (cam or {}).get("runtime") or {}
    ).get("decoder_status")
    if (preview or {}).get("degraded") or decoder == "DEGRADED":
        return "DEGRADED"
    if (preview or {}).get("stale") or decoder == "STALE":
        return "STALE"
    if decoder == "RECONNECTING" or (live or {}).get("connection_status") == "CONNECTING":
        return "RECONNECTING"
    live_ok = (
        (live or {}).get("live_decoded")
        or (live or {}).get("operationally_ready")
        or ((cam or {}).get("runtime") or {}).get("live_decoded")
    ) and decoder not in {"STOPPED", "OFFLINE"}
    if live_ok:
        return "LIVE"
    return "OFFLINE"


def mjpeg_watch(live, stale_after_ms=4000):
    if not live:
        return "UNKNOWN"
    ds = live.get("decoder_status") or ""
    if ds == "DEGRADED":
        return "DEGRADED"
    if ds in {"RECONNECTING", "CONNECTING"}:
        return "RECONNECTING"
    if ds in {"STALE", "OFFLINE", "STOPPED"}:
        return "STALE"
    age = live.get("frame_age_ms")
    if isinstance(age, (int, float)) and age > stale_after_ms:
        return "STALE"
    if ds == "OK" and live.get("live_decoded"):
        return "OK"
    return "UNKNOWN"


def test_kiem_tra_retains_both_lanes():
    hs = {"source": "rtsp_handshake", "rtsp_handshake_status": "CONFIG_SAVED", "live_decoder_operational": True}
    lg = {"source": "legacy_diagnostics", "overall_status": "PARTIAL"}
    kept = retain_both(hs, lg)
    assert kept["handshake"]["live_decoder_operational"] is True
    assert kept["legacy"]["overall_status"] == "PARTIAL"
    assert kept["handshake"]["source"] != kept["legacy"]["source"]


def test_ui_prefers_reconnecting_over_stale_live_flag():
    cam = {"runtime": {"live_decoded": True, "decoder_status": "RECONNECTING"}}
    assert ui_state(cam, None, {"decoder_status": "RECONNECTING"}) == "RECONNECTING"


def test_mjpeg_watchdog_stale_by_age():
    assert mjpeg_watch({"decoder_status": "OK", "live_decoded": True, "frame_age_ms": 9000}) == "STALE"
    assert mjpeg_watch({"decoder_status": "OK", "live_decoded": True, "frame_age_ms": 100}) == "OK"

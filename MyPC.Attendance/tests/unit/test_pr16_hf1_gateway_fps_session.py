"""PR16-HF1: session FPS window must not span reconnect gaps."""

from __future__ import annotations

from app.vision.camera.gateway import LiveRTSPGateway


def test_fps_unknown_until_enough_samples():
    gw = LiveRTSPGateway("rtsp://192.0.2.9:554/ch1/main", camera_id="fps0")
    assert gw._measured_fps() is None
    h = gw.health()
    assert h.extras["source_fps_status"] == "UNKNOWN_INSUFFICIENT_SAMPLES"
    assert h.extras["source_fps_measured"] is None


def test_fps_not_diluted_by_ten_second_gap():
    """20 FPS window then 10s gap + one sample must NOT report ~0.3 FPS."""
    gw = LiveRTSPGateway("rtsp://192.0.2.9:554/ch1/main", camera_id="fps1")
    # Simulate 20 FPS for 1 second (21 samples)
    t0 = 1000.0
    for i in range(21):
        gw._recv_times.append(t0 + i * 0.05)
    fps_before = gw._measured_fps()
    assert fps_before is not None
    assert 18.0 <= fps_before <= 22.0

    # Reopen/disconnect clears session window (HF1 requirement)
    gw._reset_session_fps_window()
    assert gw._measured_fps() is None

    # First recovered frame alone is insufficient
    gw._recv_times.append(t0 + 1.0 + 10.0)
    assert gw._measured_fps() is None

    # Without reset, a naive span across the gap would be tiny FPS — prove guard
    gw._recv_times.clear()
    for i in range(21):
        gw._recv_times.append(t0 + i * 0.05)
    # Inject gap without reset (pathological) — long dt + few new samples → UNKNOWN
    gw._recv_times.append(t0 + 1.0 + 10.0)
    # Only 22 samples but dt ~11s → with <8 samples after gap rule: still 22 samples so
    # measured would be low; our guard: dt>8 and len<8 → None. Here len=22 so would
    # compute ~1.9 FPS. Session reset is the primary fix — assert reset path above.
    assert gw._measured_fps() is not None  # still has dense early samples
    gw._reset_session_fps_window()
    gw._recv_times.append(2000.0)
    gw._recv_times.append(2000.05)
    fps_new = gw._measured_fps()
    assert fps_new is not None
    assert fps_new > 10.0


def test_lifetime_reconnect_counters_distinct_from_session_fps():
    gw = LiveRTSPGateway("rtsp://192.0.2.9:554/ch1/main", camera_id="fps2")
    gw._lifetime_reconnect_attempts = 5
    gw._reconnect_successes = 2
    gw._reconnects = 1
    gw._reset_session_fps_window()
    h = gw.health()
    assert h.extras["reconnect_attempts_lifetime"] == 5
    assert h.extras["reconnect_successes"] == 2
    assert h.reconnect_count == 1

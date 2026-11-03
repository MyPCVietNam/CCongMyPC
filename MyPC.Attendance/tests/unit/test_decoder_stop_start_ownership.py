"""P1-05: stop() must not allow a second reader while prior thread still alive."""

from __future__ import annotations

import time
from unittest import mock

from app.vision.camera.gateway import DecoderStatus, LiveRTSPGateway


def test_start_refuses_while_stop_join_still_alive():
    gw = LiveRTSPGateway("rtsp://127.0.0.1:554/x", camera_id="9")

    def blocking_loop():
        while not gw._stop.is_set():
            time.sleep(0.02)
        time.sleep(0.4)  # remain alive past short join timeout

    with mock.patch.object(gw, "_loop", blocking_loop):
        gw.start()
        assert gw._thread is not None and gw._thread.is_alive()
        prior = gw._thread
        gw.stop(join_timeout_s=0.05)
        assert gw._last_error_class == "STOP_JOIN_TIMEOUT"
        assert gw.health().decoder_status == DecoderStatus.STOPPED
        assert gw._thread is prior
        assert prior.is_alive()

        gw.start()
        assert gw._thread is prior  # no second worker

        prior.join(timeout=2.0)
        assert not prior.is_alive()
        with gw._start_lock:
            gw._thread = None
        gw.start()
        assert gw._thread is not None and gw._thread is not prior
        gw.stop(join_timeout_s=2.0)

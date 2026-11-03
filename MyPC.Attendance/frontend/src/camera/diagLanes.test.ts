import { describe, expect, it } from "vitest";
import {
  browserMjpegTransportState,
  mjpegWatchdogState,
  retainBothDiagLanes,
  serverDecoderWatchdogState,
  uiStateFromLanes,
  type LiveHealthLane,
} from "./diagLanes";

describe("diagLanes HF2", () => {
  it("retainBothDiagLanes keeps handshake and legacy after one click", () => {
    const hs = {
      source: "rtsp_handshake" as const,
      measured_at_utc: "t",
      live_decoder_operational: true,
      rtsp_handshake_status: "CONFIG_SAVED",
    };
    const lg = {
      source: "legacy_diagnostics" as const,
      measured_at_utc: "t2",
      overall_status: "PARTIAL",
    };
    const kept = retainBothDiagLanes(hs, lg);
    expect(kept.handshake?.live_decoder_operational).toBe(true);
    expect(kept.legacy?.overall_status).toBe("PARTIAL");
  });

  it("snapshot stale does not override healthy MJPEG decoder", () => {
    const live: LiveHealthLane = {
      source: "live_decoder_health",
      measured_at_utc: "t",
      camera_id: 1,
      decoder_status: "OK",
      live_decoded: true,
      operationally_ready: true,
    };
    const preview = { stale: true, decoder_status: "STALE", camera_id: 1 };
    expect(
      uiStateFromLanes({ id: 1, runtime: { live_decoded: true } }, preview, live, {
        viewMode: "mjpeg",
        selectedCameraId: 1,
      })
    ).toBe("LIVE");
    expect(
      uiStateFromLanes({ id: 1 }, preview, live, {
        viewMode: "snapshot",
        selectedCameraId: 1,
      })
    ).toBe("STALE");
  });

  it("STOPPED/RECONNECTING win over live_decoded flags", () => {
    expect(
      uiStateFromLanes(
        { runtime: { live_decoded: true, decoder_status: "RECONNECTING" } },
        null,
        {
          source: "live_decoder_health",
          measured_at_utc: "t",
          camera_id: 1,
          decoder_status: "RECONNECTING",
          live_decoded: true,
        },
        { viewMode: "mjpeg", selectedCameraId: 1 }
      )
    ).toBe("RECONNECTING");
    expect(
      uiStateFromLanes(
        { runtime: { live_decoded: true, decoder_status: "STOPPED" } },
        null,
        {
          source: "live_decoder_health",
          measured_at_utc: "t",
          camera_id: 1,
          decoder_status: "STOPPED",
          live_decoded: true,
        },
        { viewMode: "mjpeg", selectedCameraId: 1 }
      )
    ).toBe("STOPPED");
  });

  it("serverDecoderWatchdog ≠ browser MJPEG proof", () => {
    const live: LiveHealthLane = {
      source: "live_decoder_health",
      measured_at_utc: "t",
      camera_id: 1,
      decoder_status: "OK",
      live_decoded: true,
      frame_age_ms: 100,
    };
    expect(serverDecoderWatchdogState(live)).toBe("OK");
    expect(mjpegWatchdogState(live)).toBe("OK");
    expect(
      browserMjpegTransportState({
        serverWatchdog: "OK",
        lastClientActivityMs: null,
      })
    ).toBe("UNVERIFIED");
    // img onLoad-style timestamp without multipartHeartbeatVerified ⇒ still UNVERIFIED
    expect(
      browserMjpegTransportState({
        serverWatchdog: "OK",
        lastClientActivityMs: Date.now(),
        multipartHeartbeatVerified: false,
      })
    ).toBe("UNVERIFIED");
    expect(
      browserMjpegTransportState({
        serverWatchdog: "OK",
        lastClientActivityMs: Date.now() - 20_000,
        nowMs: Date.now(),
        multipartHeartbeatVerified: true,
      })
    ).toBe("STALE");
    expect(
      browserMjpegTransportState({
        serverWatchdog: "OK",
        lastClientActivityMs: Date.now(),
        nowMs: Date.now(),
        multipartHeartbeatVerified: true,
      })
    ).toBe("OK");
  });

  it("drops live lane from another camera id", () => {
    const live: LiveHealthLane = {
      source: "live_decoder_health",
      measured_at_utc: "t",
      camera_id: 99,
      decoder_status: "OK",
      live_decoded: true,
    };
    expect(
      uiStateFromLanes({ id: 1, connection_status: "CONFIG_SAVED" }, null, live, {
        viewMode: "mjpeg",
        selectedCameraId: 1,
      })
    ).toBe("CONFIG_SAVED");
  });
});

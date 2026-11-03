/**
 * Pure helpers for Camera page diagnostic lanes (PR16-HF1).
 * Handshake / legacy diagnostics / LIVE health must never overwrite each other.
 */

export type HandshakeLane = {
  source: "rtsp_handshake";
  measured_at_utc: string;
  rtsp_handshake_status?: string;
  overall_status?: string;
  handshake_only?: boolean;
  handshake_inconclusive?: boolean;
  live_decoder_operational?: boolean | null;
  connection_status_persisted?: string;
  stages?: Array<{ name: string; status: string; detail_vi: string; code?: string }>;
  note_vi?: string;
  camera_lab_pass?: boolean;
};

export type LegacyDiagLane = {
  source: "legacy_diagnostics";
  measured_at_utc: string;
  overall_status?: string;
  stages?: Array<{ name: string; status: string; detail_vi: string; code?: string }>;
  note_vi?: string;
  camera_lab_pass?: boolean;
};

export type LiveHealthLane = {
  source: "live_decoder_health";
  measured_at_utc: string;
  camera_id: number;
  decoder_status?: string;
  connection_status?: string;
  live_decoded?: boolean;
  operationally_ready?: boolean;
  fps_estimate?: number | null;
  source_fps_status?: string;
  frame_age_ms?: number | null;
  native_width?: number;
  native_height?: number;
  reconnect_count?: number;
  signed_camera_lab?: boolean;
};

export type CamRuntime = {
  bound?: boolean;
  connection_status?: string;
  live_decoded?: boolean;
  decoder_status?: string;
  native_width?: number;
  native_height?: number;
  fps_estimate?: number;
};

export type PreviewLike = {
  decoder_status?: string;
  degraded?: boolean;
  stale?: boolean;
};

/** Merge after one "Kiểm tra" click — both handshake and legacy must survive. */
export function retainBothDiagLanes(
  handshake: HandshakeLane | null,
  legacy: LegacyDiagLane | null
): { handshake: HandshakeLane | null; legacy: LegacyDiagLane | null } {
  return { handshake, legacy };
}

export function uiStateFromLanes(
  cam: { mock_mode?: boolean; connection_status?: string; live_verified?: boolean; runtime?: CamRuntime | null } | null | undefined,
  preview: PreviewLike | null | undefined,
  live: LiveHealthLane | null | undefined
): string {
  const decoder =
    live?.decoder_status || preview?.decoder_status || cam?.runtime?.decoder_status;
  if (preview?.degraded || decoder === "DEGRADED") return "DEGRADED";
  if (preview?.stale || decoder === "STALE") return "STALE";
  if (
    decoder === "RECONNECTING" ||
    live?.connection_status === "CONNECTING" ||
    cam?.runtime?.connection_status === "CONNECTING"
  )
    return "RECONNECTING";
  const liveOk =
    (live?.live_decoded || live?.operationally_ready || cam?.runtime?.live_decoded || cam?.live_verified) &&
    decoder !== "STOPPED" &&
    decoder !== "OFFLINE";
  if (liveOk) return "LIVE";
  if (cam?.mock_mode) return "MOCK";
  if (
    cam?.runtime?.connection_status === "CONFIG_SAVED" ||
    cam?.connection_status === "CONFIG_SAVED"
  )
    return "CONFIG_SAVED";
  return live?.connection_status || cam?.runtime?.connection_status || cam?.connection_status || "OFFLINE";
}

/** MJPEG <img> may stay frozen without onError — use decoder health + age. */
export function mjpegWatchdogState(
  live: LiveHealthLane | null | undefined,
  *,
  staleAfterMs = 4000
): "OK" | "STALE" | "RECONNECTING" | "DEGRADED" | "UNKNOWN" {
  if (!live) return "UNKNOWN";
  const ds = live.decoder_status || "";
  if (ds === "DEGRADED") return "DEGRADED";
  if (ds === "RECONNECTING" || ds === "CONNECTING") return "RECONNECTING";
  if (ds === "STALE" || ds === "OFFLINE" || ds === "STOPPED") return "STALE";
  const age = live.frame_age_ms;
  if (typeof age === "number" && age > staleAfterMs) return "STALE";
  if (ds === "OK" && live.live_decoded) return "OK";
  return "UNKNOWN";
}

export function nowUtcIso(): string {
  return new Date().toISOString();
}

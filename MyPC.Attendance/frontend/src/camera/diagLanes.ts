/**
 * Pure helpers for Camera page diagnostic lanes (PR16-HF2).
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
  config_revision?: string;
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
  camera_id?: number;
};

export type ViewMode = "mjpeg" | "snapshot";

export type UiStateOpts = {
  viewMode?: ViewMode;
  selectedCameraId?: number | null;
  requestGen?: number;
  liveGen?: number;
};

/** Merge after one "Kiểm tra" click — both handshake and legacy must survive. */
export function retainBothDiagLanes(
  handshake: HandshakeLane | null,
  legacy: LegacyDiagLane | null
): { handshake: HandshakeLane | null; legacy: LegacyDiagLane | null } {
  return { handshake, legacy };
}

/**
 * Prefer LIVE decoder health for MJPEG view. Snapshot preview stale/degraded
 * must NOT override a currently healthy MJPEG decoder after view-mode switch.
 */
export function uiStateFromLanes(
  cam:
    | {
        id?: number;
        mock_mode?: boolean;
        connection_status?: string;
        live_verified?: boolean;
        runtime?: CamRuntime | null;
      }
    | null
    | undefined,
  preview: PreviewLike | null | undefined,
  live: LiveHealthLane | null | undefined,
  opts: UiStateOpts = {}
): string {
  const viewMode = opts.viewMode ?? "mjpeg";
  const selectedId = opts.selectedCameraId;
  // Drop cross-camera / stale generation signals
  const liveBound =
    live &&
    (selectedId == null || live.camera_id === selectedId) &&
    (opts.liveGen == null || opts.requestGen == null || opts.liveGen === opts.requestGen)
      ? live
      : null;
  const previewBound =
    preview &&
    (preview.camera_id == null || selectedId == null || preview.camera_id === selectedId)
      ? preview
      : null;

  const decoder =
    liveBound?.decoder_status ||
    (viewMode === "snapshot" ? previewBound?.decoder_status : undefined) ||
    cam?.runtime?.decoder_status;

  // Snapshot-only degradation — ignore when viewing MJPEG with healthy decoder
  if (viewMode === "snapshot") {
    if (previewBound?.degraded || decoder === "DEGRADED") return "DEGRADED";
    if (previewBound?.stale || decoder === "STALE") return "STALE";
  } else {
    if (decoder === "DEGRADED") return "DEGRADED";
    if (decoder === "STALE") return "STALE";
  }

  if (
    decoder === "RECONNECTING" ||
    liveBound?.connection_status === "CONNECTING" ||
    cam?.runtime?.connection_status === "CONNECTING"
  )
    return "RECONNECTING";
  if (decoder === "STOPPED" || decoder === "OFFLINE") return decoder;

  const liveOk =
    (liveBound?.live_decoded ||
      liveBound?.operationally_ready ||
      cam?.runtime?.live_decoded ||
      cam?.live_verified) &&
    decoder !== "STOPPED" &&
    decoder !== "OFFLINE";
  if (liveOk) return "LIVE";
  if (cam?.mock_mode) return "MOCK";
  if (
    cam?.runtime?.connection_status === "CONFIG_SAVED" ||
    cam?.connection_status === "CONFIG_SAVED"
  )
    return "CONFIG_SAVED";
  return (
    liveBound?.connection_status ||
    cam?.runtime?.connection_status ||
    cam?.connection_status ||
    "OFFLINE"
  );
}

export type ServerDecoderWatchdog =
  | "OK"
  | "STALE"
  | "RECONNECTING"
  | "DEGRADED"
  | "UNKNOWN";

/**
 * SERVER_DECODER_WATCHDOG only — observes gateway frame_age_ms / decoder_status.
 * Does NOT prove the browser is receiving new MJPEG multipart parts.
 */
export function serverDecoderWatchdogState(
  live: LiveHealthLane | null | undefined,
  options: { staleAfterMs?: number } = {}
): ServerDecoderWatchdog {
  const staleAfterMs = options.staleAfterMs ?? 4000;
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

/** @deprecated Use serverDecoderWatchdogState — name clarified in HF2. */
export function mjpegWatchdogState(
  live: LiveHealthLane | null | undefined,
  options: { staleAfterMs?: number } = {}
): ServerDecoderWatchdog {
  return serverDecoderWatchdogState(live, options);
}

/**
 * Browser MJPEG transport freshness. Without an observable client receive
 * signal, transport is UNVERIFIED even if server decoder is OK.
 */
export function browserMjpegTransportState(opts: {
  serverWatchdog: ServerDecoderWatchdog;
  /** Monotonic client activity marker (e.g. last multipart paint / load event). */
  lastClientActivityMs?: number | null;
  nowMs?: number;
  staleAfterMs?: number;
}): "OK" | "STALE" | "UNVERIFIED" | "SERVER_NOT_OK" {
  if (opts.serverWatchdog !== "OK") return "SERVER_NOT_OK";
  const last = opts.lastClientActivityMs;
  if (last == null || !Number.isFinite(last)) return "UNVERIFIED";
  const now = opts.nowMs ?? Date.now();
  const staleAfter = opts.staleAfterMs ?? 5000;
  if (now - last > staleAfter) return "STALE";
  return "OK";
}

export function nowUtcIso(): string {
  return new Date().toISOString();
}

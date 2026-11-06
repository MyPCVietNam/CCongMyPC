import { FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/client";
import {
  HandshakeLane,
  LegacyDiagLane,
  LiveHealthLane,
  browserMjpegTransportState,
  nowUtcIso,
  retainBothDiagLanes,
  serverDecoderWatchdogState,
  uiStateFromLanes,
} from "../camera/diagLanes";
import {
  faceBoxToOverlay,
  normRectToOverlay,
  objectContainMapping,
  type NormRect,
} from "../camera/imageCoords";

type Cam = {
  id: number;
  name: string;
  host: string;
  model: string;
  firmware?: string;
  source_type?: "RTSP" | "USB_UVC" | string;
  usb_stable_id_short?: string;
  usb_friendly_name?: string;
  mock_mode: boolean;
  enabled?: boolean;
  archived?: boolean;
  has_secret: boolean;
  credential_saved?: boolean;
  username_hint?: string;
  rtsp_uri_safe?: string;
  connection_status?: string;
  live_verified?: boolean;
  last_health_status: string;
  runtime?: {
    bound?: boolean;
    connection_status?: string;
    live_decoded?: boolean;
    decoder_status?: string;
    native_width?: number;
    native_height?: number;
    fps_estimate?: number;
  } | null;
};

type UsbDeviceRow = {
  stable_id: string;
  stable_id_short?: string;
  friendly_name: string;
  index_hint?: number | null;
  ambiguous?: boolean;
  mapping_verified?: boolean;
  capture_mapping_verified?: boolean;
  trusted_live_eligible?: boolean;
  open_target?: string;
  note_vi?: string;
};

type Preview = {
  data_base64: string;
  mime: string;
  indicator_vi: string;
  width: number;
  height: number;
  mock: boolean;
  view_mode?: string;
  decoder_status?: string;
  receive_time_utc?: string;
  degraded?: boolean;
  stale?: boolean;
  ui_state?: string;
};

type QualityDiag = {
  vendor_spec?: { max_resolution?: string; status?: string };
  decoded_measured?: {
    status?: string;
    width?: number | null;
    height?: number | null;
    fps_measured?: number | null;
  };
  camera_lab_pass?: boolean;
  provenance?: string | null;
};

type FaceDetectFace = {
  x_px: number;
  y_px: number;
  w_px: number;
  h_px: number;
  score: number;
  outside_roi?: boolean;
  inter_eye_px?: number;
};

type FaceDetectResult = {
  frame_id: string;
  status: string;
  status_vi: string;
  face_count: number;
  faces: FaceDetectFace[];
  quality?: {
    ok?: boolean;
    face_width_px?: number;
    score?: number;
    reasons_vi?: string[];
    pose?: { yaw_deg?: number; pitch_deg?: number; slot_hint?: string } | null;
  };
  enrollment_gate?: string;
  enrollment_gate_vi?: string;
  inference_mode?: string;
  model_ready?: boolean;
  native_width?: number;
  native_height?: number;
  min_face_width_px?: number;
  preferred_face_width_px?: number;
  cache_hit?: boolean;
  identity_exposed?: boolean;
  attendance_written?: boolean;
  analyzed?: boolean;
  prior_analyzed_frame_id?: string | null;
  browser_mjpeg_synchronized?: boolean;
  last_analyzed_note_vi?: string;
  receive_time_utc?: string | null;
};

type Mode = "new" | "edit";
type ListFilter = "ALL" | "ACTIVE" | "MOCK" | "LIVE";

const ROI_HINT: NormRect = { x: 0.3, y: 0.05, w: 0.4, h: 0.25 };

const emptyForm = () => ({
  name: "EZVIZ H8 Pro",
  host: "",
  mock_mode: false,
  username: "",
  password: "",
  rtsp_url_override: "",
  changePassword: false,
  sourceKind: "RTSP" as "RTSP" | "USB_UVC",
  usbStableId: "",
});

export function CameraPage() {
  const [cams, setCams] = useState<Cam[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("new");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [handshake, setHandshake] = useState<HandshakeLane | null>(null);
  const [legacyDiag, setLegacyDiag] = useState<LegacyDiagLane | null>(null);
  const [liveHealth, setLiveHealth] = useState<LiveHealthLane | null>(null);
  const [quality, setQuality] = useState<QualityDiag | null>(null);
  const [analyzeMsg, setAnalyzeMsg] = useState("");
  const [roi, setRoi] = useState<NormRect>({ ...ROI_HINT });
  const [roiSaved, setRoiSaved] = useState(false);
  const [roiCalVer, setRoiCalVer] = useState(0);
  const [aiOverlay, setAiOverlay] = useState(false);
  const [faceDetect, setFaceDetect] = useState<FaceDetectResult | null>(null);
  const [faceDetectErr, setFaceDetectErr] = useState("");
  const [yunetReady, setYunetReady] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [listFilter, setListFilter] = useState<ListFilter>("ALL");
  const [showArchived, setShowArchived] = useState(false);
  const [viewMode, setViewMode] = useState<"mjpeg" | "snapshot">("mjpeg");
  const [mjpegNonce, setMjpegNonce] = useState(0);
  const [dupesMsg, setDupesMsg] = useState("");
  const [showAdmin, setShowAdmin] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [overlayBox, setOverlayBox] = useState({ w: 0, h: 0 });
  const [usbDevices, setUsbDevices] = useState<UsbDeviceRow[]>([]);
  const [usbDiagMsg, setUsbDiagMsg] = useState("");
  const selectGen = useRef(0);
  const liveHealthGen = useRef(0);
  const faceDetectGen = useRef(0);
  const hiddenRef = useRef(false);
  const inFlight = useRef(false);
  const faceInFlight = useRef(false);
  const liveImgRef = useRef<HTMLImageElement | null>(null);
  const liveWrapRef = useRef<HTMLDivElement | null>(null);
  /** Reserved for a future verified multipart frame heartbeat — never fed from img onLoad. */
  const clientMjpegActivityMs: number | null = null;

  async function reload(preferId?: number | null) {
    const qs = new URLSearchParams();
    if (showArchived) qs.set("include_archived", "true");
    if (listFilter !== "ALL") qs.set("filter", listFilter);
    const list = await api<Cam[]>(`/api/v1/cameras?${qs.toString()}`);
    setCams(list);
    const pick =
      preferId != null && list.some((c) => c.id === preferId)
        ? preferId
        : selected != null && list.some((c) => c.id === selected)
          ? selected
          : list[0]?.id ?? null;
    if (pick != null) {
      setSelected(pick);
    } else {
      setSelected(null);
      setMode("new");
      setForm(emptyForm());
    }
    return list;
  }

  function applyCamToForm(cam: Cam) {
    const kind = (cam.source_type || "RTSP").toUpperCase() === "USB_UVC" ? "USB_UVC" : "RTSP";
    setForm({
      name: cam.name || "EZVIZ H8 Pro",
      host: cam.host || "",
      mock_mode: !!cam.mock_mode,
      username: cam.username_hint || "",
      password: "",
      rtsp_url_override: cam.rtsp_uri_safe || "",
      changePassword: false,
      sourceKind: kind,
      usbStableId: "",
    });
  }

  async function loadDetail(id: number, gen: number) {
    setError("");
    setPreview(null);
    setHandshake(null);
    setLegacyDiag(null);
    setLiveHealth(null);
    setQuality(null);
    setAnalyzeMsg("");
    setFaceDetect(null);
    setFaceDetectErr("");
    setRoiSaved(false);
    try {
      const cam = await api<Cam>(`/api/v1/cameras/${id}`);
      if (gen !== selectGen.current) return;
      applyCamToForm(cam);
      setMode("edit");
      setCams((prev) => prev.map((c) => (c.id === cam.id ? { ...c, ...cam } : c)));
      setMjpegNonce((n) => n + 1);
      try {
        const regions = await api<{
          roi: NormRect | null;
          has_saved_roi?: boolean;
          calibration_version?: number;
          default_hint?: NormRect;
        }>(`/api/v1/cameras/${id}/regions`);
        if (gen !== selectGen.current) return;
        if (regions.roi) {
          setRoi({ ...regions.roi });
          setRoiSaved(true);
          setRoiCalVer(Number(regions.calibration_version || 0));
        } else {
          // Hint only — do not silently persist over DB
          setRoi({ ...(regions.default_hint || ROI_HINT) });
          setRoiSaved(false);
          setRoiCalVer(0);
        }
      } catch {
        if (gen !== selectGen.current) return;
        setRoi({ ...ROI_HINT });
        setRoiSaved(false);
      }
    } catch (err) {
      if (gen !== selectGen.current) return;
      setError(err instanceof Error ? err.message : "Không tải được camera");
    }
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [listFilter, showArchived]);

  useEffect(() => {
    if (selected == null) return;
    const gen = ++selectGen.current;
    loadDetail(selected, gen);
  }, [selected]);

  useEffect(() => {
    const onVis = () => {
      hiddenRef.current = document.hidden;
      if (!document.hidden) setMjpegNonce((n) => n + 1);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  // Per-camera LIVE decoder health refresh (does not start a second decoder)
  useEffect(() => {
    if (selected == null || mode !== "edit") return;
    let cancelled = false;
    let timer: number | undefined;
    const camId = selected;
    const gen = selectGen.current;

    const refresh = async () => {
      if (cancelled || hiddenRef.current) return;
      try {
        const h = await api<{
          sources?: Array<Record<string, unknown>>;
          signed_camera_lab?: boolean;
          ready?: boolean;
        }>(`/api/v1/cameras/gateway/health?camera_id=${camId}`);
        if (cancelled || gen !== selectGen.current || camId !== selected) return;
        const src =
          (h.sources || []).find((s) => Number(s.camera_id) === camId) || h.sources?.[0];
        if (!src) {
          liveHealthGen.current = gen;
          setLiveHealth({
            source: "live_decoder_health",
            measured_at_utc: nowUtcIso(),
            camera_id: camId,
            decoder_status: "NOT_CONFIGURED",
            live_decoded: false,
            operationally_ready: false,
          });
          return;
        }
        const extras = (src.extras as Record<string, unknown>) || {};
        liveHealthGen.current = gen;
        setLiveHealth({
          source: "live_decoder_health",
          measured_at_utc: nowUtcIso(),
          camera_id: camId,
          config_revision: String(src.config_revision || extras.config_revision || ""),
          decoder_status: String(src.decoder_status || ""),
          connection_status: String(src.connection_status || extras.connection_status || ""),
          live_decoded: Boolean(src.live_decoded ?? extras.live_decoded),
          operationally_ready: Boolean(src.operationally_ready),
          fps_estimate:
            (src.fps_estimate as number | undefined) ??
            (src.source_fps_measured as number | undefined) ??
            null,
          source_fps_status: String(src.source_fps_status || extras.source_fps_status || ""),
          frame_age_ms: (src.frame_age_ms as number | null | undefined) ?? null,
          native_width: Number(src.native_width || 0) || undefined,
          native_height: Number(src.native_height || 0) || undefined,
          reconnect_count: Number(src.reconnect_count || 0) || undefined,
          signed_camera_lab: Boolean(h.signed_camera_lab),
        });
        setCams((prev) =>
          prev.map((c) =>
            c.id === camId
              ? {
                  ...c,
                  runtime: {
                    ...(c.runtime || {}),
                    bound: true,
                    decoder_status: String(src.decoder_status || ""),
                    live_decoded: Boolean(src.live_decoded ?? extras.live_decoded),
                    connection_status: String(src.connection_status || ""),
                    native_width: Number(src.native_width || 0) || undefined,
                    native_height: Number(src.native_height || 0) || undefined,
                    fps_estimate: (src.fps_estimate as number | undefined) || undefined,
                  },
                  live_verified: Boolean(src.live_decoded ?? extras.live_decoded),
                }
              : c
          )
        );
      } catch {
        if (cancelled || gen !== selectGen.current) return;
        // Do not invent LIVE — clear ready flags on hard failure
        setLiveHealth((prev) =>
          prev && prev.camera_id === camId
            ? {
                ...prev,
                measured_at_utc: nowUtcIso(),
                decoder_status: prev.decoder_status === "OK" ? "STALE" : prev.decoder_status,
                live_decoded: false,
                operationally_ready: false,
              }
            : prev
        );
      }
    };
    refresh();
    timer = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [selected, mode]);

  // SNAPSHOT fallback poll only — labeled stills, not smooth LIVE
  useEffect(() => {
    if (selected == null || mode !== "edit" || viewMode !== "snapshot") return;
    let cancelled = false;
    let timer: number | undefined;

    const load = async () => {
      if (cancelled || hiddenRef.current || inFlight.current) return;
      const gen = selectGen.current;
      inFlight.current = true;
      try {
        const p = await api<Preview>(`/api/v1/cameras/${selected}/preview`);
        if (cancelled || gen !== selectGen.current) return;
        setPreview(p);
      } catch {
        if (cancelled || gen !== selectGen.current) return;
        setPreview(null);
      } finally {
        inFlight.current = false;
      }
    };
    load();
    timer = window.setInterval(load, 2000);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [selected, mode, viewMode]);

  function startNew() {
    selectGen.current += 1;
    setSelected(null);
    setMode("new");
    setForm(emptyForm());
    setPreview(null);
    setHandshake(null);
    setLegacyDiag(null);
    setLiveHealth(null);
    setQuality(null);
    setAnalyzeMsg("");
    setError("");
  }

  async function saveCam(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "new") {
        const payload: Record<string, unknown> = {
          name: form.name,
          host: form.sourceKind === "USB_UVC" ? "" : form.host,
          mock_mode: form.mock_mode,
          rtsp_url_override: form.sourceKind === "USB_UVC" ? "" : form.rtsp_url_override,
          username: form.sourceKind === "USB_UVC" ? "" : form.username,
          password: form.sourceKind === "USB_UVC" ? "" : form.password,
          credential_action:
            form.sourceKind === "USB_UVC" ? "keep" : form.password ? "replace" : "keep",
          source_type: form.sourceKind,
        };
        const cam = await api<Cam>("/api/v1/cameras", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await reload(cam.id);
        setSelected(cam.id);
        setMode("edit");
        setAnalyzeMsg(`Đã tạo camera #${cam.id}`);
      } else if (selected != null) {
        const payload: Record<string, unknown> = {
          name: form.name,
          host: form.host,
          mock_mode: form.mock_mode,
          rtsp_url_override: form.rtsp_url_override,
          username: form.sourceKind === "USB_UVC" ? "" : form.username,
          credential_action:
            form.sourceKind === "USB_UVC"
              ? "keep"
              : form.changePassword
                ? "replace"
                : "keep",
          password: form.sourceKind === "USB_UVC" ? "" : form.changePassword ? form.password : "",
          source_type: form.sourceKind,
          ...(form.sourceKind === "USB_UVC" && form.usbStableId
            ? { usb_stable_id: form.usbStableId }
            : {}),
        };
        const cam = await api<Cam>(`/api/v1/cameras/${selected}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        applyCamToForm(cam);
        await reload(cam.id);
        setAnalyzeMsg(`Đã lưu thay đổi camera #${cam.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi lưu camera");
    } finally {
      setBusy(false);
    }
  }

  async function archiveCam() {
    if (selected == null) return;
    const cam = cams.find((c) => c.id === selected);
    if (
      !window.confirm(
        `Lưu trữ camera #${selected} “${cam?.name || ""}”?\nLIVE sẽ dừng. Lịch sử chấm công được giữ.`
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await api(`/api/v1/cameras/${selected}/archive`, { method: "POST", body: "{}" });
      setAnalyzeMsg(`Đã lưu trữ camera #${selected}`);
      startNew();
      await reload(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi lưu trữ");
    } finally {
      setBusy(false);
    }
  }

  async function restoreCam() {
    if (selected == null) return;
    setBusy(true);
    try {
      await api(`/api/v1/cameras/${selected}/restore`, { method: "POST", body: "{}" });
      setAnalyzeMsg(`Đã khôi phục camera #${selected}`);
      setShowArchived(false);
      await reload(selected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi khôi phục");
    } finally {
      setBusy(false);
    }
  }

  async function deleteCam() {
    if (selected == null) return;
    const cam = cams.find((c) => c.id === selected);
    setBusy(true);
    try {
      const pre = await api<{
        can_hard_delete: boolean;
        prefer_archive: boolean;
        blockers: Record<string, number>;
        message_vi: string;
      }>(`/api/v1/cameras/${selected}/delete-blockers`);
      if (!pre.can_hard_delete) {
        setError(
          `${pre.message_vi} blockers=${JSON.stringify(pre.blockers)}. Hãy dùng Lưu trữ.`
        );
        return;
      }
      if (
        !window.confirm(
          `Xóa cứng camera #${selected} “${cam?.name || ""}”?\nKhông còn phụ thuộc lịch sử. Thao tác không hoàn tác.`
        )
      ) {
        return;
      }
      await api(`/api/v1/cameras/${selected}`, { method: "DELETE" });
      setAnalyzeMsg(`Đã xóa camera #${selected}`);
      startNew();
      await reload(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xóa được — hãy lưu trữ");
    } finally {
      setBusy(false);
    }
  }

  async function dryRunDupes() {
    setBusy(true);
    setDupesMsg("");
    try {
      const r = await api<{
        duplicate_groups: Array<{ cameras: Array<{ id: number; name: string }>; count: number }>;
        message_vi: string;
      }>("/api/v1/cameras/duplicates/dry-run");
      if (!r.duplicate_groups.length) {
        setDupesMsg("Không có nhóm trùng host/path đang hoạt động.");
      } else {
        const lines = r.duplicate_groups.map(
          (g) => g.cameras.map((c) => `#${c.id} ${c.name}`).join(", ")
        );
        setDupesMsg(`${r.message_vi}\n${lines.join("\n")}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi dry-run");
    } finally {
      setBusy(false);
    }
  }

  async function refreshUsbDevices() {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ devices: UsbDeviceRow[]; message_vi?: string }>(
        "/api/v1/cameras/usb/enumerate"
      );
      setUsbDevices(r.devices || []);
      setAnalyzeMsg(r.message_vi || `Tìm thấy ${r.devices?.length || 0} thiết bị USB.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi liệt kê USB");
    } finally {
      setBusy(false);
    }
  }

  async function diagnoseUsb() {
    if (!form.usbStableId) {
      setError("Chọn thiết bị USB (stable_id) trước khi đo chế độ.");
      return;
    }
    setBusy(true);
    setUsbDiagMsg("");
    try {
      const r = await api<{
        modes?: Array<Record<string, unknown>>;
        message_vi?: string;
        claims_4k?: boolean;
        mapping_verified?: boolean;
        capture_mapping_verified?: boolean;
        trusted_live_eligible?: boolean;
        ambiguous?: boolean;
        index_hint?: number | null;
        open_by_name?: boolean;
        stages?: Record<string, boolean>;
        stable_id_short?: string;
        friendly_name?: string;
      }>("/api/v1/cameras/usb/diagnose", {
        method: "POST",
        body: JSON.stringify({ stable_id: form.usbStableId }),
      });
      const lines = (r.modes || []).map(
        (m) =>
          `${m.requested}: opened=${m.opened} actual=${m.actual_width}x${m.actual_height} ` +
          `fourcc=${m.actual_fourcc || "?"} frame_ok=${m.frame_ok ?? "?"}`
      );
      const st = r.stages || {};
      setUsbDiagMsg(
        [
          r.message_vi || "",
          `thiết bị=${r.friendly_name || "?"} · id=${r.stable_id_short || "?"}`,
          `PNP_ID_FOUND=${String(!!st.PNP_ID_FOUND)} · CAPTURE_MAPPING_VERIFIED=${String(!!st.CAPTURE_MAPPING_VERIFIED)} · OPENED=${String(!!st.OPENED)} · FRAME_RECEIVED=${String(!!st.FRAME_RECEIVED)}`,
          `mapping_verified=${String(!!r.mapping_verified)} · capture_mapping_verified=${String(!!r.capture_mapping_verified)} · trusted_live_eligible=${String(!!r.trusted_live_eligible)}`,
          `ambiguous=${String(!!r.ambiguous)} · index_hint=${r.index_hint ?? "n/a"} · open_by_name=${String(!!r.open_by_name)} (always false — CAP_DSHOW index only)`,
          `claims_4k=${String(!!r.claims_4k)}`,
          ...lines,
        ].join("\n")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi chẩn đoán USB");
    } finally {
      setBusy(false);
    }
  }

  async function configureLive() {
    if (selected == null) return;
    setError("");
    if (form.sourceKind === "USB_UVC") {
      if (!form.usbStableId.trim()) {
        setError("Chọn thiết bị USB UVC (vd. UGREEN) — không dùng chỉ số OpenCV làm định danh.");
        return;
      }
      setBusy(true);
      try {
        const res = await api<{
          connection_status?: string;
          message_vi?: string;
          friendly_name?: string;
        }>(`/api/v1/cameras/gateway/live/configure-usb`, {
          method: "POST",
          body: JSON.stringify({
            camera_id: selected,
            stable_id: form.usbStableId,
            profile: "USB_MAIN",
          }),
        });
        setAnalyzeMsg(
          res.message_vi ||
            `USB gắn — ${res.connection_status || "CONFIG_SAVED"} (${res.friendly_name || ""})`
        );
        await loadDetail(selected, selectGen.current);
        setMjpegNonce((n) => n + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Lỗi gắn USB LIVE");
      } finally {
        setBusy(false);
      }
      return;
    }
    if (!form.rtsp_url_override.trim()) {
      setError("Cần URI RTSP (không nhúng mật khẩu vào URI).");
      return;
    }
    setBusy(true);
    try {
      const res = await api<{
        connection_status?: string;
        live_verified?: boolean;
        message_vi?: string;
      }>(`/api/v1/cameras/gateway/live/configure`, {
        method: "POST",
        body: JSON.stringify({
          camera_id: selected,
          rtsp_uri: form.rtsp_url_override,
          username: form.username,
          credential_action: form.changePassword ? "replace" : "keep",
          ...(form.changePassword ? { password: form.password } : {}),
          profile: "MAIN",
        }),
      });
      setAnalyzeMsg(
        res.message_vi ||
          `Đã lưu cấu hình — ${res.connection_status || "CONFIG_SAVED"} (chưa LIVE verified).`
      );
      setForm((f) => ({ ...f, password: "", changePassword: false }));
      await loadDetail(selected, selectGen.current);
      setMjpegNonce((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi gắn LIVE");
    } finally {
      setBusy(false);
    }
  }

  async function stopLive() {
    if (selected == null) return;
    setBusy(true);
    try {
      await api(`/api/v1/cameras/${selected}/gateway/stop`, { method: "POST", body: "{}" });
      setAnalyzeMsg("Đã dừng LIVE cho camera đang chọn.");
      await loadDetail(selected, selectGen.current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi dừng LIVE");
    } finally {
      setBusy(false);
    }
  }

  async function testRtsp(): Promise<HandshakeLane | null> {
    if (selected == null) return null;
    setBusy(true);
    setError("");
    try {
      const d = await api<Omit<HandshakeLane, "source" | "measured_at_utc"> & {
        measured_at_utc?: string;
        stages?: HandshakeLane["stages"];
        note_vi?: string;
        camera_lab_pass?: boolean;
      }>(`/api/v1/cameras/${selected}/rtsp/test`, {
        method: "POST",
        body: JSON.stringify({
          rtsp_uri: form.rtsp_url_override,
          username: form.username,
          ...(form.changePassword ? { password: form.password } : {}),
        }),
      });
      const lane: HandshakeLane = {
        source: "rtsp_handshake",
        measured_at_utc: d.measured_at_utc || nowUtcIso(),
        ...d,
      };
      setHandshake(lane);
      setAnalyzeMsg(
        `RTSP handshake: ${d.rtsp_handshake_status || d.overall_status || "UNKNOWN"}` +
          (d.handshake_inconclusive ? " (UNKNOWN — không ghi đè LIVE)" : "")
      );
      return lane;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi kiểm RTSP");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function runDiag(): Promise<LegacyDiagLane | null> {
    if (selected == null) return null;
    try {
      const d = await api<{
        overall_status?: string;
        stages?: LegacyDiagLane["stages"];
        note_vi?: string;
        camera_lab_pass?: boolean;
      }>(`/api/v1/cameras/${selected}/diagnostics`, {
        method: "POST",
        body: "{}",
      });
      const lane: LegacyDiagLane = {
        source: "legacy_diagnostics",
        measured_at_utc: nowUtcIso(),
        ...d,
      };
      setLegacyDiag(lane);
      return lane;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
      return null;
    }
  }

  async function loadQuality() {
    if (selected == null) return;
    try {
      const q = await api<QualityDiag>(`/api/v1/cameras/${selected}/quality/diagnostics`);
      setQuality(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function saveRoi() {
    if (selected == null) return;
    try {
      const out = await api<{
        calibration_version?: number;
        camera_lab_revoked?: boolean;
        trust_gate?: { note_vi?: string };
        message_vi?: string;
      }>(`/api/v1/cameras/${selected}/regions`, {
        method: "PUT",
        body: JSON.stringify({ name: "arrival", ...roi }),
      });
      setRoiSaved(true);
      setRoiCalVer(Number(out.calibration_version || 0));
      setAnalyzeMsg(
        `${out.message_vi || "Đã lưu vùng nhận diện."} CAMERA_LAB_HMAC_revoked=${String(
          !!out.camera_lab_revoked
        )}. ${out.trust_gate?.note_vi || ""}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  useEffect(() => {
    if (!aiOverlay || selected == null || mode !== "edit" || viewMode !== "mjpeg") {
      return;
    }
    let cancelled = false;
    const camId = selected;
    const gen = ++faceDetectGen.current;
    const tick = async () => {
      if (cancelled || hiddenRef.current || faceInFlight.current) return;
      faceInFlight.current = true;
      try {
        const d = await api<FaceDetectResult>(
          `/api/v1/cameras/${camId}/live/face-detect?max_ai_fps=2`
        );
        if (cancelled || gen !== faceDetectGen.current || camId !== selected) return;
        setFaceDetect(d);
        setFaceDetectErr("");
        setYunetReady(Boolean(d.model_ready) && d.inference_mode === "REAL");
      } catch (err) {
        if (cancelled || gen !== faceDetectGen.current) return;
        setFaceDetectErr(err instanceof Error ? err.message : "Lỗi face-detect");
        setFaceDetect(null);
      } finally {
        faceInFlight.current = false;
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 600);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [aiOverlay, selected, mode, viewMode, mjpegNonce]);

  useLayoutEffect(() => {
    const el = liveWrapRef.current;
    if (!el) return;
    const sync = () => setOverlayBox({ w: el.clientWidth, h: el.clientHeight });
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [selected, viewMode, aiOverlay]);

  const selectedCam = cams.find((c) => c.id === selected);
  const statusLabel = uiStateFromLanes(selectedCam, preview, liveHealth, {
    viewMode,
    selectedCameraId: selected,
    requestGen: selectGen.current,
    liveGen: liveHealthGen.current,
  });
  const serverWatch = serverDecoderWatchdogState(liveHealth);
  // img onLoad ≠ multipart frame heartbeat — keep browser lane UNVERIFIED (PR16-HF3)
  const browserTransport = browserMjpegTransportState({
    serverWatchdog: serverWatch,
    lastClientActivityMs: clientMjpegActivityMs,
    multipartHeartbeatVerified: false,
  });
  const displayStatus =
    viewMode === "mjpeg" &&
    (serverWatch === "STALE" || serverWatch === "RECONNECTING" || serverWatch === "DEGRADED")
      ? serverWatch
      : statusLabel;
  const mjpegSrc =
    selected != null
      ? aiOverlay
        ? `/api/v1/cameras/${selected}/preview/mjpeg-ai?max_ai_fps=2&_=${mjpegNonce}`
        : `/api/v1/cameras/${selected}/preview/mjpeg?max_fps=12&_=${mjpegNonce}`
      : "";

  const nativeW =
    faceDetect?.native_width ||
    liveHealth?.native_width ||
    liveImgRef.current?.naturalWidth ||
    2304;
  const nativeH =
    faceDetect?.native_height ||
    liveHealth?.native_height ||
    liveImgRef.current?.naturalHeight ||
    1296;
  const containMap = objectContainMapping(nativeW, nativeH, overlayBox.w, overlayBox.h);
  const draftRoiOverlay = normRectToOverlay(roi, nativeW, nativeH, containMap);

  const statusHint =
    displayStatus === "LIVE"
      ? browserTransport === "UNVERIFIED"
        ? "Server decoder LIVE — browser MJPEG transport UNVERIFIED (chưa có tín hiệu client)"
        : browserTransport === "STALE"
          ? "Server OK nhưng browser MJPEG có vẻ đóng băng (client activity stale)"
          : "Đang giải mã LIVE — chưa phải CAMERA_LAB_PASS"
      : displayStatus === "STALE"
        ? "SERVER_DECODER_WATCHDOG=STALE (không phải bằng chứng browser freeze độc lập)"
        : displayStatus === "DEGRADED"
          ? "Khung hỏng/HEVC — không dùng nhận diện. Bấm Kết nối lại."
          : displayStatus === "MOCK"
            ? "Cấu hình MOCK — không đủ bằng chứng vật lý"
            : displayStatus === "RECONNECTING" || displayStatus === "CONNECTING"
              ? "Đang kết nối / khôi phục luồng"
              : "Chưa LIVE — bấm Kết nối lại sau khi kiểm tra RTSP";

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-display">Camera</h1>
        <p className="text-sm text-muted">
          Xem LIVE, trạng thái thật, thao tác chính. Cấu hình nâng cao dành cho quản trị.{" "}
          <a className="text-brand underline" href="https://mypc.vn" target="_blank" rel="noreferrer">
            MyPC Việt Nam →
          </a>
        </p>
      </header>

      <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="text-sm space-y-1 w-full sm:min-w-[220px] sm:flex-1">
            <span className="text-muted">Camera đang chọn</span>
            <select
              className="w-full min-h-11 rounded-md bg-canvas border border-line px-3 py-2"
              value={selected ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                if (!v) {
                  startNew();
                  setEditOpen(true);
                  return;
                }
                setSelected(Number(v));
                setEditOpen(false);
              }}
            >
              <option value="">— Thêm camera mới —</option>
              {cams.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} {c.name}
                  {c.archived ? " (LƯU TRỮ)" : ""}
                  {c.mock_mode ? " · MOCK" : ""}
                  {c.live_verified || c.runtime?.live_decoded ? " · LIVE" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm flex items-center gap-2 min-h-11 sm:pb-2">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            Hiện đã lưu trữ
          </label>
          <label className="text-sm space-y-1 w-full sm:w-auto">
            <span className="text-muted block">Lọc</span>
            <select
              className="w-full sm:w-auto min-h-11 rounded-md bg-canvas border border-line px-3 py-2"
              value={listFilter}
              onChange={(e) => setListFilter(e.target.value as ListFilter)}
            >
              <option value="ALL">Tất cả</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="LIVE">LIVE</option>
              <option value="MOCK">MOCK</option>
            </select>
          </label>
        </div>
        {mode === "edit" && selected != null ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span
              className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium ${
                displayStatus === "LIVE"
                  ? "border-brand/40 text-brand bg-brand/10"
                  : displayStatus === "DEGRADED" || displayStatus === "STALE"
                    ? "border-danger/40 text-danger bg-danger/10"
                    : "border-line text-muted bg-canvas"
              }`}
            >
              {displayStatus}
            </span>
            <span className="text-xs text-muted">{statusHint}</span>
            {liveHealth ? (
              <span className="text-xs text-muted">
                {liveHealth.native_width || "?"}×{liveHealth.native_height || "?"} · FPS{" "}
                {liveHealth.source_fps_status === "UNKNOWN_INSUFFICIENT_SAMPLES"
                  ? "UNKNOWN"
                  : liveHealth.fps_estimate ?? "?"}{" "}
                · age {liveHealth.frame_age_ms ?? "?"}ms · reconnect{" "}
                {liveHealth.reconnect_count ?? 0}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="text-danger text-sm bg-danger/10 border border-danger/30 rounded-md px-3 py-2" role="alert">
          {error}
        </div>
      ) : null}
      {analyzeMsg ? <div className="text-sm text-muted">{analyzeMsg}</div> : null}
      {dupesMsg ? (
        <pre className="text-xs whitespace-pre-wrap bg-canvas border border-line rounded-md p-2">{dupesMsg}</pre>
      ) : null}

      {mode === "edit" && selected != null ? (
        <div className="rounded-xl border border-line bg-panel p-3 sm:p-4 space-y-3">
          <div
            ref={liveWrapRef}
            className="relative aspect-video bg-canvas rounded-md overflow-hidden border border-line"
          >
            {viewMode === "mjpeg" ? (
              <>
                <img
                  ref={liveImgRef}
                  alt={aiOverlay ? "LIVE MJPEG AI overlay" : "LIVE MJPEG"}
                  src={mjpegSrc}
                  className="w-full h-full object-contain"
                  onLoad={() => {
                    // Displayable once ≠ per-frame MJPEG receipt. Do not advance
                    // browser transport freshness from onLoad (stays UNVERIFIED).
                    void clientMjpegActivityMs;
                    const el = liveWrapRef.current;
                    if (el) setOverlayBox({ w: el.clientWidth, h: el.clientHeight });
                  }}
                  onError={() => {
                    if (aiOverlay) {
                      setAiOverlay(false);
                      setFaceDetectErr("Không tải được MJPEG AI — đã tắt overlay.");
                      return;
                    }
                    setViewMode("snapshot");
                  }}
                />
                {/* Client SVG: draft ROI (+ optional face boxes when metadata matches). AI MJPEG already paints server boxes. */}
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none"
                  viewBox={`0 0 ${Math.max(overlayBox.w, 1)} ${Math.max(overlayBox.h, 1)}`}
                >
                  <rect
                    x={draftRoiOverlay.x}
                    y={draftRoiOverlay.y}
                    width={draftRoiOverlay.w}
                    height={draftRoiOverlay.h}
                    fill="none"
                    stroke="rgba(80,200,255,0.85)"
                    strokeWidth={2}
                    strokeDasharray={roiSaved ? undefined : "6 4"}
                  />
                  {!aiOverlay &&
                    faceDetect?.faces?.map((f, i) => {
                      const b = faceBoxToOverlay(f, containMap);
                      return (
                        <rect
                          key={`f-${i}-${f.x_px}-${f.y_px}`}
                          x={b.x}
                          y={b.y}
                          width={b.w}
                          height={b.h}
                          fill="none"
                          stroke={f.outside_roi ? "rgba(240,80,80,0.9)" : "rgba(40,220,40,0.9)"}
                          strokeWidth={2}
                        />
                      );
                    })}
                </svg>
                <div
                  className={`absolute left-2 top-2 text-xs bg-canvas/85 border px-2 py-1 rounded ${
                    displayStatus === "LIVE"
                      ? "border-brand/40 text-brand"
                      : "border-danger/40 text-danger"
                  }`}
                >
                  {aiOverlay ? "MJPEG+AI" : "MJPEG"} · {displayStatus}
                  {serverWatch !== "OK" && serverWatch !== "UNKNOWN"
                    ? ` · SERVER_DECODER=${serverWatch}`
                    : ""}
                  {` · browser=${browserTransport}`}
                </div>
              </>
            ) : preview ? (
              <>
                <img
                  alt="Snapshot"
                  src={`data:${preview.mime};base64,${preview.data_base64}`}
                  className="w-full h-full object-contain"
                />
                <div className="absolute left-2 top-2 text-xs bg-canvas/85 border border-line px-2 py-1 rounded">
                  {preview.indicator_vi || "SNAPSHOT"}
                </div>
              </>
            ) : (
              <div className="grid place-items-center h-full text-muted text-sm px-4 text-center">
                Chưa có khung hình — bấm Kết nối lại
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded border border-line px-2 py-1">
              (a) Decoder: {displayStatus === "LIVE" ? "LIVE" : displayStatus}
            </span>
            <span className="rounded border border-line px-2 py-1">
              (b) Browser: {browserTransport}
            </span>
            <span className="rounded border border-line px-2 py-1">
              (c) YuNet REAL:{" "}
              {yunetReady == null ? "—" : yunetReady ? "READY" : "NOT_READY"}
            </span>
            <span className="rounded border border-line px-2 py-1">
              (d) Face: {faceDetect?.status || (aiOverlay ? "…" : "OFF")}
              {faceDetect?.quality?.face_width_px
                ? ` · ${faceDetect.quality.face_width_px}px`
                : ""}
            </span>
            <span className="rounded border border-line px-2 py-1">
              (e) CAMERA_LAB: {liveHealth?.signed_camera_lab ? "signed" : "—"}
            </span>
            <span className="rounded border border-line px-2 py-1">(f) FACE_PILOT: pending</span>
          </div>

          {aiOverlay ? (
            <div className="text-xs space-y-1 border border-line rounded-md p-2 bg-canvas/40">
              <div className="font-medium">
                AI — khung đã phân tích gần nhất (JSON poll ≠ đồng bộ tuyệt đối với từng JPEG MJPEG)
              </div>
              <div className="text-muted">
                Chỉ phát hiện + chất lượng — không nhận dạng / không chấm công. browser_transport vẫn
                UNVERIFIED trừ khi có telemetry multipart thật.
              </div>
              {faceDetectErr ? <div className="text-danger">{faceDetectErr}</div> : null}
              {faceDetect ? (
                <>
                  <div>
                    status={faceDetect.status}
                    {faceDetect.analyzed === false ? " (chưa phân tích frame này)" : ""} · faces=
                    {faceDetect.face_count} · last_frame={faceDetect.frame_id.slice(0, 12)} · gate=
                    {faceDetect.enrollment_gate}
                  </div>
                  <div className="text-muted">{faceDetect.status_vi}</div>
                  {faceDetect.receive_time_utc ? (
                    <div className="text-muted">receive_time_utc={faceDetect.receive_time_utc}</div>
                  ) : null}
                  {faceDetect.prior_analyzed_frame_id ? (
                    <div className="text-muted">
                      prior_analyzed={faceDetect.prior_analyzed_frame_id.slice(0, 12)}
                    </div>
                  ) : null}
                  {faceDetect.quality?.face_width_px != null ? (
                    <div>
                      face_width_px={faceDetect.quality.face_width_px} (min{" "}
                      {faceDetect.min_face_width_px ?? 120} / preferred{" "}
                      {faceDetect.preferred_face_width_px ?? 160}) · score=
                      {faceDetect.quality.score ?? "?"}
                    </div>
                  ) : null}
                  <div className="text-muted">
                    sync_claimed={String(!!faceDetect.browser_mjpeg_synchronized)} · identity_exposed=
                    {String(!!faceDetect.identity_exposed)} · attendance_written=
                    {String(!!faceDetect.attendance_written)}
                  </div>
                  {faceDetect.last_analyzed_note_vi ? (
                    <div className="text-muted">{faceDetect.last_analyzed_note_vi}</div>
                  ) : null}
                </>
              ) : (
                <div className="text-muted">Đang chờ kết quả detect…</div>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !!selectedCam?.archived}
              onClick={configureLive}
              className="rounded-md bg-brand text-canvas font-medium px-4 py-2 text-sm disabled:opacity-50"
            >
              {form.sourceKind === "USB_UVC" ? "Gắn USB LIVE" : "Kết nối lại"}
            </button>
            <label className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={aiOverlay}
                onChange={(e) => {
                  setAiOverlay(e.target.checked);
                  setFaceDetect(null);
                  setFaceDetectErr("");
                  setMjpegNonce((n) => n + 1);
                }}
              />
              AI phát hiện khuôn mặt (overlay)
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setEditOpen(true);
                setShowAdmin(true);
              }}
              className="rounded-md border border-line px-4 py-2 text-sm"
            >
              Sửa
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                const hs = await testRtsp();
                const lg = await runDiag();
                // Explicit retain — handshake must survive diagnostics overwrite (HF1 P0)
                const kept = retainBothDiagLanes(hs, lg);
                if (kept.handshake) setHandshake(kept.handshake);
                if (kept.legacy) setLegacyDiag(kept.legacy);
                await loadQuality();
              }}
              className="rounded-md border border-line px-4 py-2 text-sm"
            >
              Kiểm tra
            </button>
            <button
              type="button"
              className="rounded-md border border-line px-3 py-2 text-xs"
              onClick={() => setViewMode((m) => (m === "mjpeg" ? "snapshot" : "mjpeg"))}
            >
              {viewMode === "mjpeg" ? "Chuyển SNAPSHOT" : "Chuyển LIVE MJPEG"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={stopLive}
              className="rounded-md border border-line px-3 py-2 text-xs text-muted"
            >
              Dừng LIVE
            </button>
          </div>
        </div>
      ) : null}

      <details
        className="rounded-xl border border-line bg-panel p-4"
        open={showAdmin || mode === "new" || editOpen}
        onToggle={(e) => setShowAdmin((e.target as HTMLDetailsElement).open)}
      >
        <summary className="cursor-pointer font-medium text-sm">
          Điều khiển quản trị (nguồn camera, RTSP/USB, credential, ROI, lưu trữ/xóa)
        </summary>
        <form onSubmit={saveCam} className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Field label="Tên" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <div className="text-sm space-y-1">
            <span className="text-muted">Loại nguồn</span>
            <select
              className="w-full rounded-md bg-canvas border border-line px-3 py-2"
              value={form.sourceKind}
              onChange={(e) =>
                setForm({
                  ...form,
                  sourceKind: e.target.value === "USB_UVC" ? "USB_UVC" : "RTSP",
                })
              }
            >
              <option value="RTSP">RTSP (LAN / EZVIZ)</option>
              <option value="USB_UVC">USB (Windows UVC)</option>
            </select>
            <p className="text-xs text-muted">
              USB không thừa kế HMAC CAMERA_LAB của EZVIZ. Đổi loại nguồn sẽ thu hồi trust vật lý.
            </p>
          </div>
          {form.sourceKind === "RTSP" ? (
            <>
              <Field
                label="IP LAN (IPv4)"
                value={form.host}
                onChange={(v) => setForm({ ...form, host: v })}
              />
              <Field
                label="URI RTSP (không nhúng mật khẩu)"
                value={form.rtsp_url_override}
                onChange={(v) => setForm({ ...form, rtsp_url_override: v })}
                placeholder="rtsp://192.168.0.211:554/ch1/main"
              />
              <Field
                label="Tài khoản camera"
                value={form.username}
                onChange={(v) => setForm({ ...form, username: v })}
                autoComplete="off"
              />
              <div className="text-sm space-y-1">
                <span className="text-muted">Mật khẩu camera</span>
                {mode === "edit" && selectedCam?.credential_saved && !form.changePassword ? (
                  <div className="rounded-md border border-line bg-canvas px-3 py-2 text-muted text-xs">
                    Đã lưu — ô trống = giữ nguyên.{" "}
                    <button
                      type="button"
                      className="text-brand underline"
                      onClick={() => setForm({ ...form, changePassword: true, password: "" })}
                    >
                      Đổi mật khẩu
                    </button>
                  </div>
                ) : (
                  <input
                    type="password"
                    className="w-full rounded-md bg-canvas border border-line px-3 py-2"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    autoComplete="new-password"
                  />
                )}
              </div>
            </>
          ) : (
            <div className="sm:col-span-2 lg:col-span-2 text-sm space-y-2">
              <div className="flex flex-wrap gap-2 items-end">
                <button
                  type="button"
                  disabled={busy}
                  onClick={refreshUsbDevices}
                  className="rounded-md border border-line px-3 py-2 text-sm"
                >
                  Liệt kê USB
                </button>
                <button
                  type="button"
                  disabled={busy || !form.usbStableId}
                  onClick={diagnoseUsb}
                  className="rounded-md border border-line px-3 py-2 text-sm"
                >
                  Đo chế độ capture
                </button>
              </div>
              <label className="block space-y-1">
                <span className="text-muted">Thiết bị USB (chọn UGREEN tường minh)</span>
                <select
                  className="w-full rounded-md bg-canvas border border-line px-3 py-2"
                  value={form.usbStableId}
                  onChange={(e) => setForm({ ...form, usbStableId: e.target.value })}
                >
                  <option value="">— Chọn thiết bị —</option>
                  {usbDevices.map((d) => (
                    <option
                      key={d.stable_id}
                      value={d.stable_id}
                      disabled={!!d.ambiguous || d.trusted_live_eligible === false}
                    >
                      {d.friendly_name}
                      {d.stable_id_short ? ` (${d.stable_id_short})` : ""}
                      {d.ambiguous
                        ? " — không ổn định"
                        : d.trusted_live_eligible
                          ? " — LIVE OK"
                          : " — chưa liên kết capture"}
                    </option>
                  ))}
                </select>
              </label>
              {form.usbStableId ? (
                <p className="text-xs text-muted">
                  {(() => {
                    const d = usbDevices.find((x) => x.stable_id === form.usbStableId);
                    if (!d) return "Đã chọn stable_id — bấm Liệt kê USB nếu danh sách trống.";
                    return (
                      `Trạng thái: capture_mapping_verified=${String(!!(d.capture_mapping_verified ?? d.mapping_verified))} · ` +
                      `trusted_live=${String(!!d.trusted_live_eligible)} · ` +
                      `index_hint=${d.index_hint ?? "n/a (chưa liên kết DShow)"}` +
                      (d.note_vi ? ` — ${d.note_vi}` : "")
                    );
                  })()}
                </p>
              ) : null}
              {selectedCam?.usb_friendly_name ? (
                <p className="text-xs text-muted">
                  Đã gắn: {selectedCam.usb_friendly_name}
                  {selectedCam.usb_stable_id_short
                    ? ` · ${selectedCam.usb_stable_id_short}`
                    : ""}
                </p>
              ) : null}
              {usbDiagMsg ? (
                <pre className="text-xs whitespace-pre-wrap rounded-md border border-line bg-canvas p-2 max-h-40 overflow-auto">
                  {usbDiagMsg}
                </pre>
              ) : null}
            </div>
          )}
          <label className="text-sm flex items-end gap-2 pb-2">
            <input
              type="checkbox"
              checked={form.mock_mode}
              onChange={(e) => setForm({ ...form, mock_mode: e.target.checked })}
            />
            <span>Cấu hình MOCK (không phải LIVE runtime)</span>
          </label>
          <div className="sm:col-span-2 lg:col-span-3 flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-brand text-canvas font-medium px-4 py-2 disabled:opacity-60"
            >
              {mode === "new" ? "Tạo camera" : "Lưu thay đổi"}
            </button>
            {mode === "edit" ? (
              <>
                <button type="button" disabled={busy} onClick={dryRunDupes} className="rounded-md border border-line px-3 py-2 text-sm">
                  Dry-run trùng lặp
                </button>
                {selectedCam?.archived ? (
                  <button type="button" disabled={busy} onClick={restoreCam} className="rounded-md border border-line px-3 py-2 text-sm">
                    Khôi phục
                  </button>
                ) : (
                  <button type="button" disabled={busy} onClick={archiveCam} className="rounded-md border border-line px-3 py-2 text-sm">
                    Lưu trữ
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy}
                  onClick={deleteCam}
                  className="rounded-md border border-danger/40 text-danger px-3 py-2 text-sm"
                >
                  Xóa cứng (nếu được phép)
                </button>
              </>
            ) : null}
          </div>
        </form>

        {mode === "edit" ? (
          <div className="mt-4 border-t border-line pt-4 space-y-3">
            <p className="text-xs text-muted">
              ROI arrival {roiSaved ? `(đã lưu DB · cal_v${roiCalVer})` : "(nháp — chưa ghi DB)"}. Đường
              nét trên LIVE là bản nháp cho đến khi bấm Lưu. Đổi ROI không thu hồi CAMERA_LAB HMAC.
            </p>
            <div className="grid grid-cols-4 gap-2 text-xs">
              {(["x", "y", "w", "h"] as const).map((k) => (
                <label key={k} className="space-y-1">
                  <span className="text-muted uppercase">ROI {k}</span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    className="w-full rounded-md bg-canvas border border-line px-2 py-1"
                    value={roi[k]}
                    onChange={(e) => {
                      setRoi({ ...roi, [k]: Number(e.target.value) });
                      setRoiSaved(false);
                    }}
                  />
                </label>
              ))}
            </div>
            <button type="button" onClick={saveRoi} className="rounded-md border border-line px-3 py-1.5 text-sm">
              Lưu vùng nhận diện
            </button>
            {handshake ? (
              <ul className="text-xs space-y-1 border border-line rounded-md p-2">
                <li className="font-medium text-ink">
                  Lane RTSP handshake · đo {handshake.measured_at_utc}
                </li>
                <li className="text-brand">
                  {handshake.rtsp_handshake_status || handshake.overall_status || "?"}
                  {handshake.handshake_only ? " (HANDSHAKE_ONLY)" : ""}
                  {handshake.handshake_inconclusive ? " · UNKNOWN không ghi đè DB" : ""}
                </li>
                <li>
                  LIVE decoder operational (tại lúc probe):{" "}
                  {handshake.live_decoder_operational == null
                    ? "không xác định"
                    : String(handshake.live_decoder_operational)}
                </li>
                {handshake.connection_status_persisted ? (
                  <li>DB connection_status: {handshake.connection_status_persisted}</li>
                ) : null}
                {handshake.stages?.map((s) => (
                  <li key={`hs-${s.name}`}>
                    {s.name}: {s.status} — {s.detail_vi}
                  </li>
                ))}
              </ul>
            ) : null}
            {legacyDiag ? (
              <ul className="text-xs space-y-1 border border-line rounded-md p-2 mt-2">
                <li className="font-medium text-ink">
                  Lane diagnostics legacy · đo {legacyDiag.measured_at_utc}
                </li>
                {legacyDiag.overall_status ? <li>Tổng: {legacyDiag.overall_status}</li> : null}
                {legacyDiag.stages?.map((s) => (
                  <li key={`lg-${s.name}`}>
                    {s.name}: {s.status} — {s.detail_vi}
                  </li>
                ))}
                <li className="text-muted">
                  CAMERA_LAB_PASS={String(legacyDiag.camera_lab_pass)} (chỉ ký HMAC)
                </li>
              </ul>
            ) : null}
            {liveHealth ? (
              <ul className="text-xs space-y-1 border border-line rounded-md p-2 mt-2">
                <li className="font-medium text-ink">
                  Lane LIVE decoder · đo {liveHealth.measured_at_utc}
                </li>
                <li>
                  {liveHealth.decoder_status} · fps_status={liveHealth.source_fps_status || "?"} ·
                  signed_camera_lab={String(!!liveHealth.signed_camera_lab)}
                </li>
              </ul>
            ) : null}
            {quality ? (
              <div className="text-xs text-muted">
                DECODED {quality.decoded_measured?.width}×{quality.decoded_measured?.height} · FPS{" "}
                {quality.decoded_measured?.fps_measured ?? "?"} · provenance {quality.provenance || "?"}
              </div>
            ) : null}
            <p className="text-xs text-muted">
              A/B vật lý: chỉ đổi một biến mỗi lần (H.265↔H.264, TCP↔UDP, Wi-Fi↔RJ45). Ghi log gián đoạn/khôi phục.
            </p>
          </div>
        ) : null}
      </details>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="text-sm space-y-1">
      <span className="text-muted">{label}</span>
      <input
        className="w-full rounded-md bg-canvas border border-line px-3 py-2"
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

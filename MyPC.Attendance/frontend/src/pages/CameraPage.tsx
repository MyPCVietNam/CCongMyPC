import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

type Cam = {
  id: number;
  name: string;
  host: string;
  model: string;
  firmware?: string;
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

type Diag = {
  stages: Array<{ name: string; status: string; detail_vi: string; code?: string }>;
  camera_lab_pass: boolean;
  note_vi: string;
  overall_status?: string;
  indicator_vi?: string;
  handshake_only?: boolean;
  rtsp_handshake_status?: string;
  live_decoder_operational?: boolean | null;
  connection_status_persisted?: string;
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

type Mode = "new" | "edit";
type ListFilter = "ALL" | "ACTIVE" | "MOCK" | "LIVE";

const emptyForm = () => ({
  name: "EZVIZ H8 Pro",
  host: "",
  mock_mode: false,
  username: "",
  password: "",
  rtsp_url_override: "",
  changePassword: false,
});

function uiStateFromCam(cam?: Cam | null, preview?: Preview | null): string {
  // Decoder lane first — never let handshake CONFIG_SAVED / LIVE chip race (PR16 S2/S6)
  if (preview?.degraded || preview?.decoder_status === "DEGRADED") return "DEGRADED";
  if (preview?.stale || preview?.decoder_status === "STALE") return "STALE";
  if (
    cam?.runtime?.decoder_status === "RECONNECTING" ||
    cam?.runtime?.connection_status === "CONNECTING" ||
    preview?.decoder_status === "RECONNECTING"
  )
    return "RECONNECTING";
  if (
    (cam?.runtime?.live_decoded || cam?.live_verified) &&
    cam?.runtime?.decoder_status !== "STOPPED" &&
    cam?.runtime?.decoder_status !== "OFFLINE"
  )
    return "LIVE";
  if (cam?.mock_mode) return "MOCK";
  // Handshake-only DB status — not LIVE
  if (cam?.runtime?.connection_status === "CONFIG_SAVED" || cam?.connection_status === "CONFIG_SAVED")
    return "CONFIG_SAVED";
  return cam?.runtime?.connection_status || cam?.connection_status || "OFFLINE";
}

export function CameraPage() {
  const [cams, setCams] = useState<Cam[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("new");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [diag, setDiag] = useState<Diag | null>(null);
  const [quality, setQuality] = useState<QualityDiag | null>(null);
  const [analyzeMsg, setAnalyzeMsg] = useState("");
  const [roi, setRoi] = useState({ x: 0.3, y: 0.05, w: 0.4, h: 0.25 });
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
  const selectGen = useRef(0);
  const hiddenRef = useRef(false);
  const inFlight = useRef(false);

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
    setForm({
      name: cam.name || "EZVIZ H8 Pro",
      host: cam.host || "",
      mock_mode: !!cam.mock_mode,
      username: cam.username_hint || "",
      password: "",
      rtsp_url_override: cam.rtsp_uri_safe || "",
      changePassword: false,
    });
  }

  async function loadDetail(id: number, gen: number) {
    setError("");
    setPreview(null);
    setDiag(null);
    setQuality(null);
    setAnalyzeMsg("");
    try {
      const cam = await api<Cam>(`/api/v1/cameras/${id}`);
      if (gen !== selectGen.current) return;
      applyCamToForm(cam);
      setMode("edit");
      setCams((prev) => prev.map((c) => (c.id === cam.id ? { ...c, ...cam } : c)));
      setMjpegNonce((n) => n + 1);
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
    setDiag(null);
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
          host: form.host,
          mock_mode: form.mock_mode,
          rtsp_url_override: form.rtsp_url_override,
          username: form.username,
          password: form.password,
          credential_action: form.password ? "replace" : "keep",
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
          username: form.username,
          credential_action: form.changePassword ? "replace" : "keep",
          password: form.changePassword ? form.password : "",
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

  async function configureLive() {
    if (selected == null) return;
    setError("");
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

  async function testRtsp() {
    if (selected == null) return;
    setBusy(true);
    setError("");
    try {
      const d = await api<Diag>(`/api/v1/cameras/${selected}/rtsp/test`, {
        method: "POST",
        body: JSON.stringify({
          rtsp_uri: form.rtsp_url_override,
          username: form.username,
          ...(form.changePassword ? { password: form.password } : {}),
        }),
      });
      setDiag(d);
      setAnalyzeMsg(`Kết quả kiểm RTSP: ${d.overall_status || "UNKNOWN"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi kiểm RTSP");
    } finally {
      setBusy(false);
    }
  }

  async function runDiag() {
    if (selected == null) return;
    try {
      const d = await api<Diag>(`/api/v1/cameras/${selected}/diagnostics`, {
        method: "POST",
        body: "{}",
      });
      setDiag(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
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
      await api(`/api/v1/cameras/${selected}/regions`, {
        method: "PUT",
        body: JSON.stringify({ name: "arrival", ...roi }),
      });
      setAnalyzeMsg("Đã lưu vùng nhận diện.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  const selectedCam = cams.find((c) => c.id === selected);
  const statusLabel = uiStateFromCam(selectedCam, preview);
  const mjpegSrc =
    selected != null
      ? `/api/v1/cameras/${selected}/preview/mjpeg?max_fps=12&_=${mjpegNonce}`
      : "";

  const statusHint =
    statusLabel === "LIVE"
      ? "Đang giải mã LIVE — chưa phải CAMERA_LAB_PASS"
      : statusLabel === "DEGRADED"
        ? "Khung hỏng/HEVC — không dùng nhận diện. Bấm Kết nối lại."
        : statusLabel === "MOCK"
          ? "Cấu hình MOCK — không đủ bằng chứng vật lý"
          : statusLabel === "RECONNECTING" || statusLabel === "CONNECTING"
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
                statusLabel === "LIVE"
                  ? "border-brand/40 text-brand bg-brand/10"
                  : statusLabel === "DEGRADED"
                    ? "border-danger/40 text-danger bg-danger/10"
                    : "border-line text-muted bg-canvas"
              }`}
            >
              {statusLabel}
            </span>
            <span className="text-xs text-muted">{statusHint}</span>
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
          <div className="relative aspect-video bg-canvas rounded-md overflow-hidden border border-line">
            {viewMode === "mjpeg" ? (
              <>
                <img
                  alt="LIVE MJPEG"
                  src={mjpegSrc}
                  className="w-full h-full object-contain"
                  onError={() => setViewMode("snapshot")}
                />
                <div className="absolute left-2 top-2 text-xs bg-canvas/85 border border-brand/40 text-brand px-2 py-1 rounded">
                  LIVE MJPEG · {statusLabel}
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
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !!selectedCam?.archived}
              onClick={configureLive}
              className="rounded-md bg-brand text-canvas font-medium px-4 py-2 text-sm disabled:opacity-50"
            >
              Kết nối lại
            </button>
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
                await testRtsp();
                await runDiag();
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
          Điều khiển quản trị (RTSP, credential, ROI, lưu trữ/xóa)
        </summary>
        <form onSubmit={saveCam} className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Field label="Tên" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <Field label="IP LAN (IPv4)" value={form.host} onChange={(v) => setForm({ ...form, host: v })} />
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
                    onChange={(e) => setRoi({ ...roi, [k]: Number(e.target.value) })}
                  />
                </label>
              ))}
            </div>
            <button type="button" onClick={saveRoi} className="rounded-md border border-line px-3 py-1.5 text-sm">
              Lưu vùng nhận diện
            </button>
            {diag ? (
              <ul className="text-xs space-y-1">
                <li className="text-brand">
                  RTSP handshake: {diag.rtsp_handshake_status || diag.overall_status || "?"}
                  {diag.handshake_only ? " (HANDSHAKE_ONLY — ≠ LIVE decoder)" : ""}
                </li>
                <li>
                  LIVE decoder đang chạy:{" "}
                  {diag.live_decoder_operational == null
                    ? "không xác định"
                    : String(diag.live_decoder_operational)}
                </li>
                {diag.connection_status_persisted ? (
                  <li>DB connection_status giữ: {diag.connection_status_persisted}</li>
                ) : null}
                {diag.stages?.map((s) => (
                  <li key={s.name}>
                    {s.name}: {s.status} — {s.detail_vi}
                    {s.name.toUpperCase().includes("ONVIF") ? " (UNVERIFIED nếu chưa đo)" : ""}
                    {s.name.toUpperCase().includes("FIRST") ? " (probe ≠ decoded LIVE)" : ""}
                  </li>
                ))}
                {diag.note_vi ? <li className="text-muted">{diag.note_vi}</li> : null}
                <li className="text-muted">CAMERA_LAB_PASS={String(diag.camera_lab_pass)} (chỉ ký HMAC)</li>
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

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
};

type Diag = {
  stages: Array<{ name: string; status: string; detail_vi: string; code?: string }>;
  camera_lab_pass: boolean;
  note_vi: string;
  overall_status?: string;
  indicator_vi?: string;
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

const emptyForm = () => ({
  name: "EZVIZ H8 Pro",
  host: "",
  mock_mode: false,
  username: "",
  password: "",
  rtsp_url_override: "",
  changePassword: false,
});

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
  const [pollErrorStreak, setPollErrorStreak] = useState(0);
  const selectGen = useRef(0);
  const hiddenRef = useRef(false);

  async function reload(preferId?: number | null) {
    const list = await api<Cam[]>("/api/v1/cameras");
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
    setPollErrorStreak(0);
    try {
      const cam = await api<Cam>(`/api/v1/cameras/${id}`);
      if (gen !== selectGen.current) return;
      applyCamToForm(cam);
      setMode("edit");
      setCams((prev) => prev.map((c) => (c.id === cam.id ? { ...c, ...cam } : c)));
    } catch (err) {
      if (gen !== selectGen.current) return;
      setError(err instanceof Error ? err.message : "Không tải được camera");
    }
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (selected == null) return;
    const gen = ++selectGen.current;
    loadDetail(selected, gen);
  }, [selected]);

  useEffect(() => {
    const onVis = () => {
      hiddenRef.current = document.hidden;
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (selected == null || mode !== "edit") return;
    let cancelled = false;
    let timer: number | undefined;
    const delay = pollErrorStreak >= 3 ? 8000 : 1500;

    const load = () => {
      if (cancelled || hiddenRef.current) return;
      const gen = selectGen.current;
      api<Preview>(`/api/v1/cameras/${selected}/preview`)
        .then((p) => {
          if (cancelled || gen !== selectGen.current) return;
          setPreview(p);
          setPollErrorStreak(0);
        })
        .catch(() => {
          if (cancelled || gen !== selectGen.current) return;
          setPreview(null);
          setPollErrorStreak((n) => n + 1);
        });
    };
    load();
    timer = window.setInterval(load, delay);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [selected, mode, pollErrorStreak >= 3 ? 1 : 0]);

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

  async function deleteCam() {
    if (selected == null) return;
    const cam = cams.find((c) => c.id === selected);
    if (
      !window.confirm(
        `Xóa cứng camera #${selected} “${cam?.name || ""}”?\nChỉ thành công nếu không còn dữ liệu lịch sử. Nên dùng Lưu trữ.`
      )
    ) {
      return;
    }
    setBusy(true);
    try {
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
  const statusLabel =
    selectedCam?.runtime?.live_decoded || selectedCam?.live_verified
      ? "LIVE đã giải mã (chưa CAMERA_LAB)"
      : selectedCam?.runtime?.connection_status ||
        selectedCam?.connection_status ||
        (selectedCam?.mock_mode ? "MOCK cấu hình" : "Chưa xác minh");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Quản lý Camera & RTSP</h1>
        <p className="text-sm text-muted mt-1">
          Chọn camera để sửa — mật khẩu đã lưu không bao giờ hiện lại. TCP mở ≠ LIVE.{" "}
          <a className="text-brand underline" href="https://mypc.vn" target="_blank" rel="noreferrer">
            MyPC Viet Nam
          </a>
        </p>
      </header>

      <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm space-y-1 min-w-[220px] flex-1">
            <span className="text-muted">Camera đang chọn</span>
            <select
              className="w-full rounded-md bg-canvas border border-line px-3 py-2"
              value={selected ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                if (!v) {
                  startNew();
                  return;
                }
                setSelected(Number(v));
              }}
            >
              <option value="">— Thêm camera mới —</option>
              {cams.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} {c.name} {c.mock_mode ? "(cấu hình MOCK)" : ""}{" "}
                  {c.live_verified || c.runtime?.live_decoded ? "· LIVE" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={startNew}
            className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel2"
          >
            Thêm camera mới
          </button>
          {mode === "edit" && selected != null ? (
            <span className="text-xs text-muted pb-2">
              Trạng thái: <strong className="text-ink">{statusLabel}</strong>
            </span>
          ) : null}
        </div>
      </div>

      <form
        onSubmit={saveCam}
        className="rounded-xl border border-line bg-panel p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        <Field label="Tên" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
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
            <div className="rounded-md border border-line bg-canvas px-3 py-2 text-muted">
              Đã lưu credential — ô trống = giữ nguyên.{" "}
              <button
                type="button"
                className="text-brand underline"
                onClick={() => setForm({ ...form, changePassword: true, password: "" })}
              >
                Đổi mật khẩu camera
              </button>
            </div>
          ) : (
            <input
              type="password"
              className="w-full rounded-md bg-canvas border border-line px-3 py-2"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="new-password"
              placeholder={mode === "edit" ? "Mật khẩu mới" : "Mật khẩu"}
            />
          )}
          {form.changePassword ? (
            <button
              type="button"
              className="text-xs text-muted underline"
              onClick={() => setForm({ ...form, changePassword: false, password: "" })}
            >
              Hủy đổi mật khẩu
            </button>
          ) : null}
        </div>
        <label className="text-sm flex items-end gap-2 pb-2">
          <input
            type="checkbox"
            checked={form.mock_mode}
            onChange={(e) => setForm({ ...form, mock_mode: e.target.checked })}
          />
          <span>Cấu hình chế độ mô phỏng (không phải trạng thái runtime)</span>
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
              <button
                type="button"
                disabled={busy}
                onClick={configureLive}
                className="rounded-md border border-brand/40 text-brand px-3 py-2 text-sm"
              >
                Kết nối LIVE
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={stopLive}
                className="rounded-md border border-line px-3 py-2 text-sm"
              >
                Dừng LIVE
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={testRtsp}
                className="rounded-md border border-line px-3 py-2 text-sm"
              >
                Kiểm RTSP
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={archiveCam}
                className="rounded-md border border-line px-3 py-2 text-sm"
              >
                Lưu trữ camera
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={deleteCam}
                className="rounded-md border border-danger/40 text-danger px-3 py-2 text-sm"
              >
                Xóa cứng (nếu không có lịch sử)
              </button>
            </>
          ) : null}
        </div>
      </form>

      {error ? (
        <div className="text-danger text-sm bg-danger/10 border border-danger/30 rounded-md px-3 py-2">
          {error}
        </div>
      ) : null}
      {analyzeMsg ? <div className="text-sm text-muted">{analyzeMsg}</div> : null}

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium">Xem trước</h2>
          <div className="relative aspect-video bg-canvas rounded-md overflow-hidden border border-line">
            {preview ? (
              <>
                <img
                  alt="Xem trước camera"
                  src={`data:${preview.mime};base64,${preview.data_base64}`}
                  className="w-full h-full object-contain"
                />
                <div
                  className="absolute border-2 border-brand/80 pointer-events-none"
                  style={{
                    left: `${roi.x * 100}%`,
                    top: `${roi.y * 100}%`,
                    width: `${roi.w * 100}%`,
                    height: `${roi.h * 100}%`,
                  }}
                />
                <div className="absolute left-2 top-2 text-xs bg-canvas/80 border border-brand/40 text-brand px-2 py-1 rounded">
                  {preview.indicator_vi}
                </div>
              </>
            ) : (
              <div className="grid place-items-center h-full text-muted text-sm px-4 text-center">
                {mode === "new"
                  ? "Chọn hoặc tạo camera để xem trước"
                  : pollErrorStreak >= 3
                    ? "Tạm dừng poll nhanh — chưa có khung hình / lỗi kéo dài"
                    : "Chưa có khung hình giải mã"}
              </div>
            )}
          </div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            {(["x", "y", "w", "h"] as const).map((k) => (
              <label key={k} className="space-y-1">
                <span className="text-muted uppercase">{k}</span>
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
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={saveRoi}
              disabled={selected == null}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Lưu vùng nhận diện
            </button>
            <button
              type="button"
              onClick={runDiag}
              disabled={selected == null}
              className="rounded-md bg-brand/15 border border-brand/40 text-brand px-3 py-1.5 text-sm"
            >
              Chẩn đoán nhanh
            </button>
            <button
              type="button"
              onClick={loadQuality}
              disabled={selected == null}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Đo chất lượng ảnh
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-line bg-panel p-4 space-y-3 text-sm">
          <h2 className="font-medium">Chẩn đoán / chất lượng</h2>
          {diag ? (
            <ul className="space-y-1">
              {diag.overall_status ? (
                <li className="font-medium">Tổng: {diag.overall_status}</li>
              ) : null}
              {diag.stages?.map((s) => (
                <li key={s.name}>
                  <span className="text-muted">{s.name}</span>: {s.status} — {s.detail_vi}
                </li>
              ))}
              <li className="text-muted text-xs">{diag.note_vi}</li>
              <li className="text-xs">CAMERA_LAB_PASS={String(diag.camera_lab_pass)}</li>
            </ul>
          ) : (
            <p className="text-muted">Chưa chạy kiểm RTSP / chẩn đoán.</p>
          )}
          {quality ? (
            <div className="border-t border-line pt-3 space-y-1 text-xs">
              <div>
                DECODED_MEASURED: {quality.decoded_measured?.width ?? "?"}×
                {quality.decoded_measured?.height ?? "?"} · FPS{" "}
                {quality.decoded_measured?.fps_measured ?? "?"}
              </div>
              <div>Provenance: {quality.provenance || "UNKNOWN"}</div>
              <div>CAMERA_LAB_PASS={String(quality.camera_lab_pass)}</div>
            </div>
          ) : null}
          <p className="text-xs text-muted">
            Đường dẫn gợi ý (thủ công, không tự dò): /ch1/main · /h264/ch1/main/av_stream ·
            /Streaming/Channels/101 — xác nhận theo firmware thiết bị.
          </p>
        </div>
      </div>
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

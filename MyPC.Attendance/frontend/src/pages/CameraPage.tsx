import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Cam = {
  id: number;
  name: string;
  host: string;
  model: string;
  mock_mode: boolean;
  last_health_status: string;
  has_secret: boolean;
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
  stages: Array<{ name: string; status: string; detail_vi: string }>;
  camera_lab_pass: boolean;
  note_vi: string;
  indicator_vi?: string;
};

type QualityDiag = {
  vendor_spec?: { max_resolution?: string; status?: string };
  decoded_measured?: {
    status?: string;
    width?: number | null;
    height?: number | null;
    fps_measured?: number | null;
    clock_trust?: string | null;
    pixel_sha256?: string | null;
  };
  auto_enhance?: { requested?: string; effective?: string; note_vi?: string };
  camera_lab_pass?: boolean;
  provenance?: string | null;
  config_revision?: string | null;
};

export function CameraPage() {
  const [cams, setCams] = useState<Cam[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [diag, setDiag] = useState<Diag | null>(null);
  const [quality, setQuality] = useState<QualityDiag | null>(null);
  const [analyzeMsg, setAnalyzeMsg] = useState("");
  const [roi, setRoi] = useState({ x: 0.3, y: 0.05, w: 0.4, h: 0.25 });
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "EZVIZ H8 Pro",
    host: "",
    mock_mode: true,
    username: "",
    password: "",
    rtsp_url_override: "",
  });

  async function reload() {
    const list = await api<Cam[]>("/api/v1/cameras");
    setCams(list);
    if (list.length && selected == null) setSelected(list[0].id);
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (selected == null) return;
    const load = () =>
      api<Preview>(`/api/v1/cameras/${selected}/preview`)
        .then((p) => {
          setPreview(p);
          setError("");
        })
        .catch((e) => {
          setPreview(null);
          setError(e.message);
        });
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [selected]);

  async function createCam(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const cam = await api<Cam>("/api/v1/cameras", {
        method: "POST",
        body: JSON.stringify(form),
      });
      await reload();
      setSelected(cam.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function runDiag() {
    if (selected == null) return;
    setError("");
    try {
      const d = await api<Diag>(`/api/v1/cameras/${selected}/diagnostics`, {
        method: "POST",
      });
      setDiag(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function loadQuality() {
    if (selected == null) return;
    setError("");
    try {
      const q = await api<QualityDiag>(`/api/v1/cameras/${selected}/quality/diagnostics`);
      setQuality(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function analyzeOnce() {
    if (selected == null) return;
    setAnalyzeMsg("");
    try {
      const r = await api<{
        original_unchanged: boolean;
        enhancement_status: string;
        applied_methods: string[];
        note_vi: string;
      }>(`/api/v1/cameras/${selected}/quality/analyze-once`, {
        method: "POST",
        body: "{}",
      });
      const paired = (r as { paired?: { blockers?: string[]; status?: string } }).paired;
      setAnalyzeMsg(
        `${r.note_vi} · gốc giữ nguyên=${r.original_unchanged ? "có" : "không"} · ${r.enhancement_status} · ${r.applied_methods.join(",") || "không xử lý"}` +
          (paired ? ` · paired=${paired.status || "?"} blockers=${(paired.blockers || []).join("|") || "không"}` : "")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function revertAuto() {
    if (selected == null) return;
    try {
      const r = await api<{ effective_mode: string }>(
        `/api/v1/cameras/${selected}/quality/settings`,
        {
          method: "PUT",
          body: JSON.stringify({
            requested_mode: "AUTO",
            revert: true,
            reverted_reason: "OPERATOR_ROLLBACK",
          }),
        }
      );
      setAnalyzeMsg(`Đã khôi phục cấu hình an toàn · hiệu lực=${r.effective_mode}`);
      await loadQuality();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function exportReport() {
    if (selected == null) return;
    try {
      const res = await fetch(`/api/v1/cameras/${selected}/quality/report?download=true`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Không xuất được báo cáo");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mypc-camera-${selected}-quality-report.json`;
      a.click();
      URL.revokeObjectURL(url);
      setAnalyzeMsg("Đã tải báo cáo JSON đã ẩn thông tin nhạy cảm.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function configureLive() {
    if (selected == null) return;
    setError("");
    if (!form.rtsp_url_override.trim()) {
      setError("Cần URI RTSP (không nhúng mật khẩu vào URI).");
      return;
    }
    try {
      await api(`/api/v1/cameras/gateway/live/configure`, {
        method: "POST",
        body: JSON.stringify({
          camera_id: selected,
          rtsp_uri: form.rtsp_url_override,
          username: form.username,
          password: form.password,
          profile: "MAIN",
        }),
      });
      setAnalyzeMsg("Đã gắn gateway LIVE (CAMERA_LAB_PASS vẫn chưa đạt).");
      await loadQuality();
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Camera & Chất lượng hình ảnh</h1>
        <p className="text-sm text-muted mt-1">
          Thông số hãng (VENDOR_SPEC) ≠ kích thước đã giải mã (DECODED_MEASURED). Preview đã thu nhỏ không
          thay thế ảnh gốc. Chế độ “Tự động” hiện hành: AUTO_TEST_ONLY (ảnh gốc chính thức).{" "}
          <a className="text-brand underline" href="https://mypc.vn" target="_blank" rel="noreferrer">
            MyPC Viet Nam
          </a>
        </p>
      </header>

      <form
        onSubmit={createCam}
        className="rounded-xl border border-line bg-panel p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        <Field label="Tên" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <Field
          label="IP / Hostname"
          value={form.host}
          onChange={(v) => setForm({ ...form, host: v })}
        />
        <Field
          label="RTSP thủ công (tuỳ chọn)"
          value={form.rtsp_url_override}
          onChange={(v) => setForm({ ...form, rtsp_url_override: v })}
        />
        <Field
          label="Tài khoản camera"
          value={form.username}
          onChange={(v) => setForm({ ...form, username: v })}
        />
        <label className="text-sm space-y-1">
          <span className="text-muted">Mật khẩu camera</span>
          <input
            type="password"
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete="new-password"
          />
        </label>
        <label className="text-sm flex items-end gap-2 pb-2">
          <input
            type="checkbox"
            checked={form.mock_mode}
            onChange={(e) => setForm({ ...form, mock_mode: e.target.checked })}
          />
          <span>Chế độ mô phỏng</span>
        </label>
        <div className="sm:col-span-2 lg:col-span-3">
          <button type="submit" className="rounded-md bg-brand text-canvas font-medium px-4 py-2">
            Thêm camera
          </button>
        </div>
      </form>

      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-medium">Xem trước</h2>
            <select
              className="rounded-md bg-canvas border border-line px-2 py-1 text-sm"
              value={selected ?? ""}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {cams.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} {c.name} {c.mock_mode ? "(mô phỏng)" : ""}
                </option>
              ))}
            </select>
          </div>
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
              <div className="grid place-items-center h-full text-muted text-sm">
                Chưa có khung hình
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
              className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel2"
            >
              Lưu vùng nhận diện
            </button>
            <button
              type="button"
              onClick={runDiag}
              className="rounded-md bg-brand/15 border border-brand/40 text-brand px-3 py-1.5 text-sm"
            >
              Kiểm tra camera
            </button>
            <button
              type="button"
              onClick={configureLive}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Gắn nguồn LIVE
            </button>
            <button
              type="button"
              onClick={loadQuality}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Đo chất lượng ảnh
            </button>
            <button
              type="button"
              onClick={analyzeOnce}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              So sánh nhận diện gốc/xử lý (shadow)
            </button>
            <button
              type="button"
              onClick={revertAuto}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Khôi phục cấu hình
            </button>
            <button
              type="button"
              onClick={exportReport}
              className="rounded-md border border-line px-3 py-1.5 text-sm"
            >
              Xuất báo cáo đã ẩn thông tin nhạy cảm
            </button>
          </div>
          {analyzeMsg && <p className="text-xs text-muted">{analyzeMsg}</p>}
        </div>

        <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium">Kết quả chẩn đoán</h2>
          {!diag && <p className="text-sm text-muted">Chưa chạy kiểm tra.</p>}
          {diag && (
            <>
              <p className="text-sm text-muted">{diag.note_vi}</p>
              <p className="text-sm">
                CAMERA_LAB_PASS:{" "}
                <span className={diag.camera_lab_pass ? "text-ok" : "text-warn"}>
                  {diag.camera_lab_pass ? "PASS" : "CHƯA ĐẠT"}
                </span>
              </p>
              <ul className="space-y-2 text-sm">
                {diag.stages.map((s) => (
                  <li
                    key={s.name}
                    className="rounded-md border border-line bg-canvas px-3 py-2 flex gap-3"
                  >
                    <span className="font-mono text-xs text-brand w-24 shrink-0">{s.status}</span>
                    <span>
                      <div className="font-medium">{s.name}</div>
                      <div className="text-muted text-xs mt-0.5">{s.detail_vi}</div>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h2 className="font-medium pt-2">Chất lượng hình ảnh</h2>
          {!quality && <p className="text-sm text-muted">Chưa đo — nhấn “Đo chất lượng ảnh”.</p>}
          {quality && (
            <div className="text-sm space-y-2">
              <p>
                VENDOR_SPEC tối đa: {quality.vendor_spec?.max_resolution || "—"} (
                {quality.vendor_spec?.status || "—"})
              </p>
              <p>
                DECODED_MEASURED:{" "}
                {quality.decoded_measured?.width && quality.decoded_measured?.height
                  ? `${quality.decoded_measured.width}×${quality.decoded_measured.height}`
                  : "Chưa xác minh"}{" "}
                · FPS đo: {quality.decoded_measured?.fps_measured ?? "—"} · Đồng hồ:{" "}
                {quality.decoded_measured?.clock_trust || "—"}
              </p>
              <p>
                Provenance: {quality.provenance || "—"} · Hiệu lực xử lý ảnh:{" "}
                {quality.auto_enhance?.effective || "OFF"}
              </p>
              <p className="text-xs text-muted">{quality.auto_enhance?.note_vi}</p>
              <p className="text-xs font-mono break-all text-muted">
                SHA256 gốc: {quality.decoded_measured?.pixel_sha256 || "—"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="text-sm space-y-1 block">
      <span className="text-muted">{label}</span>
      <input
        className="w-full rounded-md bg-canvas border border-line px-3 py-2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

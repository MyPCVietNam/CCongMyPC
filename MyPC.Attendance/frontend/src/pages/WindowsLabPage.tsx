import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Cam = { id: number; name: string; host: string; mock_mode: boolean };

type LabRun = {
  run_id: string;
  kind: string;
  state: string;
  decoded_w?: number | null;
  decoded_h?: number | null;
  fps_measured?: number | null;
  challenge_issued?: boolean;
  face_validation_status?: string | null;
  review_kind?: string;
  note_vi?: string;
  camera_lab_pass?: boolean;
  face_pilot_pass?: boolean;
  evidence_layers?: Record<string, boolean>;
};

/**
 * Secure operator workflow: session cookie stays in the browser (HttpOnly path),
 * CSRF via in-memory header from login — never pasted into PowerShell.
 */
export function WindowsLabPage() {
  const [cams, setCams] = useState<Cam[]>([]);
  const [cameraId, setCameraId] = useState<number | null>(null);
  const [kind, setKind] = useState<"CAMERA_LAB" | "FACE_PILOT">("CAMERA_LAB");
  const [run, setRun] = useState<LabRun | null>(null);
  const [challenge, setChallenge] = useState("");
  const [ack, setAck] = useState(
    "Tôi xác nhận đây là xác nhận một toán tử trên máy Windows LAN (không phải review độc lập hai bên)."
  );
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [evidenceId, setEvidenceId] = useState("");

  useEffect(() => {
    api<Cam[]>("/api/v1/cameras")
      .then((list) => {
        setCams(list);
        if (list.length) setCameraId(list[0].id);
      })
      .catch((e) => setErr(e.message));
  }, []);

  async function startRun(e: FormEvent) {
    e.preventDefault();
    if (cameraId == null) return;
    setErr("");
    setMsg("");
    setChallenge("");
    setEvidenceId("");
    try {
      const r = await api<LabRun>(`/api/v1/cameras/${cameraId}/lab-runs`, {
        method: "POST",
        body: JSON.stringify({ kind, profile: "MAIN" }),
      });
      setRun(r);
      setMsg(`Đã tạo lab run ${r.run_id} — challenge không hiển thị ở đây cho đến khi bấm lấy challenge.`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function measure() {
    if (cameraId == null || !run) return;
    setErr("");
    try {
      const r = await api<LabRun>(`/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/measure`, {
        method: "POST",
        body: JSON.stringify({ samples: 5 }),
      });
      setRun(r);
      setMsg(
        `LIVE_SOURCE_MEASURED: ${r.decoded_w}x${r.decoded_h} @ ${r.fps_measured?.toFixed?.(2) ?? r.fps_measured} FPS (khung phân biệt).`
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function fetchChallenge() {
    if (cameraId == null || !run) return;
    setErr("");
    try {
      const r = await api<{ owner_challenge: string }>(
        `/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/owner-challenge`,
        { method: "POST", body: "{}" }
      );
      setChallenge(r.owner_challenge);
      setMsg("Đã lấy challenge một lần vào bộ nhớ trình duyệt — không lưu JSON/log.");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function ownerReview() {
    if (cameraId == null || !run) return;
    setErr("");
    try {
      const r = await api<LabRun>(
        `/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/owner-review`,
        {
          method: "POST",
          body: JSON.stringify({ challenge, ack_vi: ack }),
        }
      );
      setRun(r);
      setChallenge(""); // clear from memory after use
      setMsg(`Owner review: ${r.state} (${r.review_kind}). face_validation=${r.face_validation_status}`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function promote() {
    if (cameraId == null || !run) return;
    setErr("");
    try {
      const r = await api<{ evidence_id: string; evidence_class: string; camera_lab_pass: boolean }>(
        `/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/promote-physical`,
        { method: "POST", body: "{}" }
      );
      setEvidenceId(r.evidence_id);
      setMsg(
        `Evidence ${r.evidence_id} class=${r.evidence_class}. camera_lab_pass=${r.camera_lab_pass} — vẫn cần ký phê duyệt riêng; cổng vật lý có thể vẫn BLOCKED.`
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl text-ink">Windows Lab (P02S)</h1>
        <p className="text-sm text-muted mt-1">
          Quy trình an toàn trên localhost: không dán cookie/CSRF/challenge vào PowerShell.
          CAMERA_LAB / FACE_PILOT / INSTALLER vẫn BLOCKED cho đến khi có bằng chứng LAN thật.
          Owner review là xác nhận <strong>một toán tử</strong>, không phải review độc lập hai bên.
        </p>
      </div>

      <form onSubmit={startRun} className="space-y-3 rounded-md border border-line bg-panel p-4">
        <label className="block text-sm">
          Camera
          <select
            className="mt-1 w-full rounded-md border border-line bg-panel2 px-3 py-2"
            value={cameraId ?? ""}
            onChange={(e) => setCameraId(Number(e.target.value))}
          >
            {cams.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.id} {c.name} {c.mock_mode ? "(MOCK)" : ""} {c.host}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Loại lab
          <select
            className="mt-1 w-full rounded-md border border-line bg-panel2 px-3 py-2"
            value={kind}
            onChange={(e) => setKind(e.target.value as "CAMERA_LAB" | "FACE_PILOT")}
          >
            <option value="CAMERA_LAB">CAMERA_LAB (kết nối / LIVE decode)</option>
            <option value="FACE_PILOT">FACE_PILOT (cần case CORRECT đủ sàn — không đếm WRONG/FA)</option>
          </select>
        </label>
        <button type="submit" className="rounded-md bg-brand/90 text-white px-4 py-2 text-sm">
          1. Bắt đầu lab run
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={measure} className="rounded-md border border-line px-3 py-2 text-sm">
          2. Đo LIVE (khung phân biệt)
        </button>
        <button
          type="button"
          onClick={fetchChallenge}
          className="rounded-md border border-line px-3 py-2 text-sm"
        >
          3. Lấy challenge (trình duyệt)
        </button>
        <button
          type="button"
          onClick={ownerReview}
          className="rounded-md border border-line px-3 py-2 text-sm"
        >
          4. Owner review
        </button>
        <button type="button" onClick={promote} className="rounded-md border border-line px-3 py-2 text-sm">
          5. Promote PHYSICAL
        </button>
      </div>

      <label className="block text-sm">
        Xác nhận (ack_vi)
        <textarea
          className="mt-1 w-full rounded-md border border-line bg-panel2 px-3 py-2 min-h-[72px]"
          value={ack}
          onChange={(e) => setAck(e.target.value)}
        />
      </label>

      {challenge ? (
        <p className="text-xs text-muted">
          Challenge đang giữ trong bộ nhớ UI (không ghi file). Độ dài: {challenge.length} ký tự.
        </p>
      ) : null}

      {run ? (
        <pre className="text-xs bg-panel2 border border-line rounded-md p-3 overflow-auto">
          {JSON.stringify(
            {
              run_id: run.run_id,
              kind: run.kind,
              state: run.state,
              decoded: `${run.decoded_w}x${run.decoded_h}`,
              fps_measured: run.fps_measured,
              layers: run.evidence_layers,
              face_validation_status: run.face_validation_status,
              review_kind: run.review_kind,
              camera_lab_pass: run.camera_lab_pass,
              face_pilot_pass: run.face_pilot_pass,
              note_vi: run.note_vi,
              evidence_id: evidenceId || null,
            },
            null,
            2
          )}
        </pre>
      ) : null}

      {msg ? <p className="text-sm text-brand">{msg}</p> : null}
      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      <p className="text-xs text-muted">
        FACE_PILOT case (KNOWN/UNKNOWN) ghi qua API có consent_ack_vi trên cùng phiên đăng nhập; điều
        kiện ánh sáng là nhãn toán tử, không phải đo tự động. Không xuất ảnh/embedding.
      </p>
    </div>
  );
}

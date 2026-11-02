import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Cam = { id: number; name: string; host: string; mock_mode: boolean; archived?: boolean };

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
  next_action?: string;
  next_action_vi?: string;
  allowed_actions?: string[];
  checklist?: Record<string, unknown>;
  distinctions_vi?: Record<string, string>;
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
  const [showJson, setShowJson] = useState(false);

  useEffect(() => {
    api<Cam[]>("/api/v1/cameras")
      .then((list) => {
        const physical = list.filter((c) => !c.mock_mode && !c.archived);
        setCams(physical.length ? physical : list);
        if (physical.length) setCameraId(physical[0].id);
        else if (list.length) setCameraId(list[0].id);
      })
      .catch((e) => setErr(e.message));
  }, []);

  function allowed(action: string): boolean {
    if (!run?.allowed_actions) return true;
    return run.allowed_actions.includes(action);
  }

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
      setMsg(r.next_action_vi || `Đã tạo lab run ${r.run_id}`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function measure() {
    if (cameraId == null || !run) return;
    if (!allowed("measure")) {
      setErr(run.next_action_vi || "Không đo được ở trạng thái hiện tại.");
      return;
    }
    setErr("");
    try {
      const r = await api<LabRun>(`/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/measure`, {
        method: "POST",
        body: JSON.stringify({ samples: 5 }),
      });
      setRun(r);
      setMsg(
        `LIVE_SOURCE_MEASURED: ${r.decoded_w}x${r.decoded_h} @ ${r.fps_measured?.toFixed?.(2) ?? r.fps_measured} FPS. ${r.next_action_vi || ""}`
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function fetchChallenge() {
    if (cameraId == null || !run) return;
    if (!allowed("reveal_challenge")) {
      setErr(
        run.state === "OWNER_REVIEWED" || run.state === "PHYSICAL_VERIFIED"
          ? "Challenge chỉ mở khi LIVE_MEASURED — run đã qua bước này. Hãy Promote hoặc tạo run mới."
          : run.next_action_vi || "Challenge chưa sẵn sàng."
      );
      return;
    }
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
    if (!allowed("owner_review")) {
      setErr(
        run.state === "OWNER_REVIEWED"
          ? "Owner review đã xong — bước tiếp theo là Promote PHYSICAL."
          : run.next_action_vi || "Owner review cần LIVE_MEASURED."
      );
      return;
    }
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
      setChallenge("");
      setMsg(`Owner review: ${r.state} (${r.review_kind}). ${r.next_action_vi || ""}`);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function promote() {
    if (cameraId == null || !run) return;
    if (!allowed("promote_physical")) {
      setErr(run.next_action_vi || "Chưa thể promote.");
      return;
    }
    setErr("");
    try {
      const r = await api<{ evidence_id: string; evidence_class: string; camera_lab_pass: boolean }>(
        `/api/v1/cameras/${cameraId}/lab-runs/${run.run_id}/promote-physical`,
        { method: "POST", body: "{}" }
      );
      setEvidenceId(r.evidence_id);
      setRun((prev) =>
        prev
          ? {
              ...prev,
              state: "PHYSICAL_VERIFIED",
              next_action: "DONE_AWAITING_SIGNED_APPROVAL",
              allowed_actions: ["export_json"],
              camera_lab_pass: false,
            }
          : prev
      );
      setMsg(
        `Evidence ${r.evidence_id} class=${r.evidence_class}. ` +
          `PHYSICAL_VERIFIED ≠ camera_lab_pass (vẫn ${String(r.camera_lab_pass)}). ` +
          `Cần phê duyệt HMAC riêng; cổng vật lý có thể vẫn BLOCKED.`
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  const checklist = run?.checklist || {};
  const faceLabel =
    kind === "CAMERA_LAB"
      ? "N/A (CAMERA_LAB không duyệt nhận diện)"
      : String(run?.face_validation_status || checklist.face_pilot || "PENDING");

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl text-ink">Windows Lab</h1>
        <p className="text-sm text-muted mt-1">
          Wizard toán tử: chỉ hiện bước hợp lệ. Không dán cookie/CSRF/challenge vào PowerShell.
          CAMERA_LAB / FACE_PILOT / INSTALLER vẫn BLOCKED cho đến khi có bằng chứng LAN thật.
          Owner review là xác nhận <strong>một toán tử</strong>, không phải review độc lập hai bên.
        </p>
      </div>

      <form onSubmit={startRun} className="space-y-3 rounded-md border border-line bg-panel p-4">
        <label className="block text-sm">
          Camera vật lý (ưu tiên không MOCK)
          <select
            className="mt-1 w-full rounded-md border border-line bg-panel2 px-3 py-2"
            value={cameraId ?? ""}
            onChange={(e) => setCameraId(Number(e.target.value))}
          >
            {cams.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.id} {c.name} {c.mock_mode ? "(MOCK — không đủ PHYSICAL)" : ""} {c.host}
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
            <option value="FACE_PILOT">FACE_PILOT (case CORRECT đủ sàn — không đếm WRONG/FA)</option>
          </select>
        </label>
        <button type="submit" className="rounded-md bg-brand/90 text-white px-4 py-2 text-sm">
          1. Bắt đầu lab run mới
        </button>
      </form>

      {run ? (
        <div className="rounded-md border border-line bg-panel p-4 space-y-3 text-sm">
          <div className="font-medium">Bước tiếp theo</div>
          <p className="text-brand">{run.next_action_vi || run.state}</p>
          <ul className="text-xs space-y-1">
            <li>Lab run: {String(checklist.lab_run_created ?? true)}</li>
            <li>LIVE_SOURCE_MEASURED: {String(checklist.LIVE_SOURCE_MEASURED ?? false)}</li>
            <li>
              PHYSICAL_CONNECTIVITY_REVIEWED:{" "}
              {String(checklist.PHYSICAL_CONNECTIVITY_REVIEWED ?? false)}
            </li>
            <li>Evidence PHYSICAL: {String(checklist.evidence_physical_record ?? false)}</li>
            <li>camera_lab_pass (HMAC): luôn false cho đến khi ký riêng</li>
            <li>FACE_PILOT: {faceLabel}</li>
          </ul>
          {run.distinctions_vi ? (
            <details className="text-xs text-muted">
              <summary>Phân biệt lớp bằng chứng</summary>
              <ul className="mt-1 space-y-1">
                {Object.entries(run.distinctions_vi).map(([k, v]) => (
                  <li key={k}>
                    <strong>{k}</strong>: {v}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={measure}
          disabled={!run || !allowed("measure")}
          className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40"
        >
          2. Đo LIVE
        </button>
        <button
          type="button"
          onClick={fetchChallenge}
          disabled={!run || !allowed("reveal_challenge")}
          className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40"
        >
          3. Lấy challenge
        </button>
        <button
          type="button"
          onClick={ownerReview}
          disabled={!run || !allowed("owner_review")}
          className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40"
        >
          4. Owner review
        </button>
        <button
          type="button"
          onClick={promote}
          disabled={!run || !allowed("promote_physical")}
          className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40"
        >
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

      <label className="text-xs flex items-center gap-2">
        <input type="checkbox" checked={showJson} onChange={(e) => setShowJson(e.target.checked)} />
        Hiện JSON kỹ thuật (nâng cao)
      </label>

      {run && showJson ? (
        <pre className="text-xs bg-panel2 border border-line rounded-md p-3 overflow-auto">
          {JSON.stringify(
            {
              run_id: run.run_id,
              kind: run.kind,
              state: run.state,
              next_action: run.next_action,
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
        MOCK / khung stale / cùng frame / sai camera không bao giờ promote PHYSICAL. Không xuất
        ảnh/embedding mặc định.
      </p>
    </div>
  );
}

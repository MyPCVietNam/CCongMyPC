import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

type WizardStep = {
  id: string;
  title: string;
  action?: string;
  doneWhen?: (run: LabRun | null) => boolean;
};

const STEPS: WizardStep[] = [
  { id: "start", title: "Bắt đầu lab run" },
  {
    id: "measure",
    title: "Đo LIVE nguồn",
    action: "measure",
    doneWhen: (r) => Boolean(r && ["LIVE_MEASURED", "OWNER_REVIEWED", "PHYSICAL_VERIFIED"].includes(r.state)),
  },
  {
    id: "challenge",
    title: "Lấy challenge (một lần)",
    action: "reveal_challenge",
    doneWhen: (r) => Boolean(r && ["OWNER_REVIEWED", "PHYSICAL_VERIFIED"].includes(r.state)),
  },
  {
    id: "review",
    title: "Owner review",
    action: "owner_review",
    doneWhen: (r) => Boolean(r && ["OWNER_REVIEWED", "PHYSICAL_VERIFIED"].includes(r.state)),
  },
  {
    id: "promote",
    title: "Promote PHYSICAL",
    action: "promote_physical",
    doneWhen: (r) => r?.state === "PHYSICAL_VERIFIED",
  },
];

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
  const [busy, setBusy] = useState(false);

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

  const activeStepId = useMemo(() => {
    if (!run) return "start";
    if (run.state === "PHYSICAL_VERIFIED") return "done";
    const acts = run.allowed_actions || [];
    if (acts.includes("measure")) return "measure";
    if (acts.includes("reveal_challenge") && !challenge) return "challenge";
    if (acts.includes("owner_review") || (acts.includes("reveal_challenge") && challenge)) return "review";
    if (acts.includes("promote_physical")) return "promote";
    return "done";
  }, [run, challenge]);

  async function startRun(e: FormEvent) {
    e.preventDefault();
    if (cameraId == null) return;
    setBusy(true);
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
    } finally {
      setBusy(false);
    }
  }

  async function measure() {
    if (cameraId == null || !run) return;
    if (!allowed("measure")) {
      setErr(run.next_action_vi || "Không đo được ở trạng thái hiện tại.");
      return;
    }
    setBusy(true);
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
    } finally {
      setBusy(false);
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
    setBusy(true);
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
    } finally {
      setBusy(false);
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
    if (!challenge.trim()) {
      setErr("Cần lấy challenge trước khi xác nhận owner review.");
      return;
    }
    setBusy(true);
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
    } finally {
      setBusy(false);
    }
  }

  async function promote() {
    if (cameraId == null || !run) return;
    if (!allowed("promote_physical")) {
      setErr(run.next_action_vi || "Chưa thể promote.");
      return;
    }
    setBusy(true);
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
          `Cần phê duyệt HMAC riêng; cổng vật lý vẫn BLOCKED cho đến khi có bằng chứng owner.`
      );
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  const checklist = run?.checklist || {};
  const faceLabel =
    kind === "CAMERA_LAB"
      ? "N/A (CAMERA_LAB không duyệt nhận diện)"
      : String(run?.face_validation_status || checklist.face_pilot || "PENDING");

  const disabledReason = (action: string): string | null => {
    if (!run) return "Hãy bắt đầu lab run trước.";
    if (allowed(action)) return null;
    return run.next_action_vi || `Bước “${action}” chưa sẵn sàng (state=${run.state}).`;
  };

  return (
    <div className="space-y-5 max-w-3xl">
      <header className="space-y-1">
        <p className="text-xs text-muted">
          <Link to="/cai-dat" className="text-brand hover:underline">
            ← Cài đặt
          </Link>
          <span className="mx-2">·</span>
          Quản trị / Windows Lab
        </p>
        <h1 className="font-display text-2xl text-ink">Windows Lab</h1>
        <p className="text-sm text-muted">
          Wizard từng bước: chỉ hiện hành động hợp lệ tiếp theo. Cookie/CSRF/challenge không được dán vào
          PowerShell. CAMERA_LAB / FACE_PILOT / INSTALLER vẫn BLOCKED đến khi có bằng chứng LAN thật.
        </p>
      </header>

      <ol className="flex flex-wrap gap-2 text-xs" aria-label="Tiến trình lab">
        {STEPS.map((s, i) => {
          const done = s.id === "start" ? Boolean(run) : Boolean(s.doneWhen?.(run));
          const active = activeStepId === s.id;
          return (
            <li
              key={s.id}
              className={`rounded-md border px-2.5 py-1 ${
                active
                  ? "border-brand/40 bg-brand/10 text-brand"
                  : done
                    ? "border-line bg-panel2 text-ink"
                    : "border-line text-muted"
              }`}
            >
              {i + 1}. {s.title}
            </li>
          );
        })}
      </ol>

      {activeStepId === "start" ? (
        <form onSubmit={startRun} className="space-y-3 rounded-xl border border-line bg-panel p-4">
          <h2 className="font-medium text-sm">Bước 1 — Bắt đầu lab run</h2>
          <label className="block text-sm">
            Camera vật lý (ưu tiên không MOCK)
            <select
              className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2"
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
              className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2"
              value={kind}
              onChange={(e) => setKind(e.target.value as "CAMERA_LAB" | "FACE_PILOT")}
            >
              <option value="CAMERA_LAB">CAMERA_LAB (kết nối / LIVE decode)</option>
              <option value="FACE_PILOT">FACE_PILOT (case CORRECT đủ sàn)</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || cameraId == null}
            className="rounded-md bg-brand text-canvas px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Bắt đầu lab run mới
          </button>
        </form>
      ) : null}

      {run && activeStepId === "measure" ? (
        <section className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium text-sm">Bước 2 — Đo LIVE nguồn</h2>
          <p className="text-sm text-muted">
            {run.next_action_vi || "Đo độ phân giải / FPS từ decoder LIVE (không dùng MOCK/stale)."}
          </p>
          <button
            type="button"
            onClick={measure}
            disabled={busy || !allowed("measure")}
            title={disabledReason("measure") || undefined}
            className="rounded-md bg-brand text-canvas px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Đo LIVE ngay
          </button>
          {!allowed("measure") ? (
            <p className="text-xs text-muted">{disabledReason("measure")}</p>
          ) : null}
        </section>
      ) : null}

      {run && activeStepId === "challenge" ? (
        <section className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium text-sm">Bước 3 — Lấy challenge</h2>
          <p className="text-sm text-muted">
            Challenge chỉ mở một lần, giữ trong bộ nhớ trình duyệt — không ghi file/log.
          </p>
          <button
            type="button"
            onClick={fetchChallenge}
            disabled={busy || !allowed("reveal_challenge")}
            title={disabledReason("reveal_challenge") || undefined}
            className="rounded-md bg-brand text-canvas px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Lấy challenge
          </button>
          {challenge ? (
            <p className="text-xs text-muted">Đã giữ challenge trong UI · độ dài {challenge.length} ký tự.</p>
          ) : null}
        </section>
      ) : null}

      {run && activeStepId === "review" ? (
        <section className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium text-sm">Bước 4 — Owner review (một toán tử)</h2>
          <label className="block text-sm">
            Xác nhận (ack_vi)
            <textarea
              className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 min-h-[72px]"
              value={ack}
              onChange={(e) => setAck(e.target.value)}
            />
          </label>
          {!challenge ? (
            <p className="text-xs text-danger">Chưa có challenge — lấy ở bước 3 trước.</p>
          ) : null}
          <button
            type="button"
            onClick={ownerReview}
            disabled={busy || !allowed("owner_review") || !challenge}
            title={disabledReason("owner_review") || undefined}
            className="rounded-md bg-brand text-canvas px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Xác nhận owner review
          </button>
        </section>
      ) : null}

      {run && activeStepId === "promote" ? (
        <section className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <h2 className="font-medium text-sm">Bước 5 — Promote PHYSICAL</h2>
          <p className="text-sm text-muted">
            Tạo evidence PHYSICAL. physical_verified ≠ camera_lab_pass (HMAC ký riêng). Cổng vật lý vẫn
            BLOCKED đến khi owner cung cấp bằng chứng.
          </p>
          <button
            type="button"
            onClick={promote}
            disabled={busy || !allowed("promote_physical")}
            title={disabledReason("promote_physical") || undefined}
            className="rounded-md bg-brand text-canvas px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Promote PHYSICAL
          </button>
        </section>
      ) : null}

      {run && activeStepId === "done" ? (
        <section className="rounded-xl border border-line bg-panel p-4 space-y-2 text-sm">
          <h2 className="font-medium">Hoàn tất workflow lab run</h2>
          <p className="text-muted">
            state={run.state}. Evidence {evidenceId || "(chưa promote)"}. camera_lab_pass vẫn false cho đến
            khi ký HMAC — cổng CAMERA_LAB / FACE_PILOT / INSTALLER = BLOCKED.
          </p>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-2 text-sm"
            onClick={() => {
              setRun(null);
              setChallenge("");
              setEvidenceId("");
              setMsg("");
            }}
          >
            Tạo lab run mới
          </button>
        </section>
      ) : null}

      {msg ? <p className="text-sm text-brand" role="status">{msg}</p> : null}
      {err ? (
        <p className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-md px-3 py-2" role="alert">
          {err}
        </p>
      ) : null}

      <details className="rounded-xl border border-line bg-panel p-4 text-sm">
        <summary className="cursor-pointer font-medium">Chi tiết kỹ thuật (JSON / HMAC / provenance)</summary>
        <div className="mt-3 space-y-2 text-xs text-muted">
          <ul className="space-y-1">
            <li>Lab run: {String(checklist.lab_run_created ?? Boolean(run))}</li>
            <li>LIVE_SOURCE_MEASURED: {String(checklist.LIVE_SOURCE_MEASURED ?? false)}</li>
            <li>
              PHYSICAL_CONNECTIVITY_REVIEWED:{" "}
              {String(checklist.PHYSICAL_CONNECTIVITY_REVIEWED ?? false)}
            </li>
            <li>Evidence PHYSICAL: {String(checklist.evidence_physical_record ?? false)}</li>
            <li>camera_lab_pass (HMAC): luôn false đến khi ký riêng</li>
            <li>FACE_PILOT: {faceLabel}</li>
          </ul>
          {run?.distinctions_vi ? (
            <ul className="space-y-1">
              {Object.entries(run.distinctions_vi).map(([k, v]) => (
                <li key={k}>
                  <strong className="text-ink">{k}</strong>: {v}
                </li>
              ))}
            </ul>
          ) : null}
          {run ? (
            <pre className="bg-canvas border border-line rounded-md p-3 overflow-auto whitespace-pre-wrap">
              {JSON.stringify(
                {
                  run_id: run.run_id,
                  kind: run.kind,
                  state: run.state,
                  next_action: run.next_action,
                  allowed_actions: run.allowed_actions,
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
          ) : (
            <p>Chưa có lab run.</p>
          )}
        </div>
      </details>

      <p className="text-xs text-muted">
        MOCK / khung stale / cùng frame / sai camera không bao giờ promote PHYSICAL. Không xuất
        ảnh/embedding mặc định.
      </p>
    </div>
  );
}

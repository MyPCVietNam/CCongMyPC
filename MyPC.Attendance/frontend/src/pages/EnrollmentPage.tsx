import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

type Emp = { id: number; code: string; full_name: string; biometric_eligible: boolean };

type AutoSession = {
  session_id: string;
  enrollment_id: number;
  status: string;
  ui_state: string;
  current_step: string;
  guidance_vi: string;
  completed_slots: string[];
  required_slots: string[];
  face_done: number;
  body_done: number;
  message_vi?: string;
  announcement_vi?: string;
  accepted?: boolean;
  roi_required?: boolean;
  inference_mode?: string;
};

const FACE_SLOTS = ["FACE_FRONT", "FACE_LEFT", "FACE_RIGHT"] as const;
const BODY_SLOTS = ["BODY_FRONT", "BODY_LEFT", "BODY_RIGHT", "BODY_MOTION"] as const;

const SLOT_LABEL: Record<string, string> = {
  FACE_FRONT: "Nhìn thẳng",
  FACE_LEFT: "Xoay trái",
  FACE_RIGHT: "Xoay phải",
  BODY_FRONT: "Toàn thân nhìn thẳng",
  BODY_LEFT: "Toàn thân nghiêng trái",
  BODY_RIGHT: "Toàn thân nghiêng phải",
  BODY_MOTION: "Toàn thân đang chuyển động",
};

const STATE_HELP: Record<string, string> = {
  WAITING_FOR_PERSON: "Chờ nhân viên vào khung hình toàn cảnh.",
  MULTIPLE_PEOPLE: "Nhiều người — chỉ giữ đúng nhân viên đang đăng ký.",
  TOO_FAR: "Đứng gần camera hơn để khuôn mặt đủ lớn.",
  BLURRY: "Ảnh mờ — giữ yên và nhìn rõ.",
  TOO_DARK: "Thiếu sáng — cải thiện đèn.",
  FACE_OCCLUDED: "Khuôn mặt bị che — bỏ mũ/khẩu trang nếu có thể.",
  TURN_LEFT: "Xoay mặt sang trái của bạn.",
  TURN_RIGHT: "Xoay mặt sang phải của bạn.",
  BODY_NOT_FULLY_VISIBLE: "Chưa thấy đủ đầu và chân.",
  CHECKING_IDENTITY: "Đang kiểm tra danh tính…",
  SAMPLE_ACCEPTED: "Đã nhận mẫu.",
  READY_TO_ACTIVATE: "Đủ mẫu — sẵn sàng kích hoạt sau xác minh.",
  ACTIVE: "Đăng ký đang hiệu lực.",
  CAMERA_DISCONNECTED: "Mất kết nối camera.",
  NEEDS_REVIEW: "Cần đối soát thủ công.",
  BLOCKED_BY_CAMERA_GEOMETRY: "Camera không đủ góc/pixel toàn thân — không bịa hoàn thành.",
  BODY_CAPTURE_BLOCKED: "Thu toàn thân bị chặn do hình học camera.",
  PAUSED: "Phiên tạm dừng.",
};

function speakVi(text: string, enabled: boolean) {
  if (!enabled || typeof window === "undefined" || !window.speechSynthesis) return;
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "vi-VN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch {
    /* offline / no voice — text + optional beep remain */
  }
}

function beep(enabled: boolean) {
  if (!enabled || typeof window === "undefined") return;
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.connect(g);
    g.connect(ctx.destination);
    o.frequency.value = 880;
    g.gain.value = 0.04;
    o.start();
    setTimeout(() => {
      o.stop();
      ctx.close();
    }, 120);
  } catch {
    /* ignore */
  }
}

export function EnrollmentPage() {
  const [emps, setEmps] = useState<Emp[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [ack, setAck] = useState(false);
  const [authRef, setAuthRef] = useState("HR-");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [fixtureKey, setFixtureKey] = useState("");
  const [session, setSession] = useState<AutoSession | null>(null);
  const [soundOn, setSoundOn] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [lastQuality, setLastQuality] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([
      api<Emp[]>("/api/v1/employees"),
      api<Record<string, unknown>>("/api/v1/face/status"),
    ])
      .then(([e, s]) => {
        setEmps(e);
        setStatus(s);
      })
      .catch((e) => setError(e.message));
  }, []);

  const progressPct = useMemo(() => {
    if (!session) return 0;
    const n = (session.completed_slots || []).length;
    return Math.round((n / 7) * 100);
  }, [session]);

  async function startAuto(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    if (!ack) {
      setError("Cần xác nhận thông báo xử lý dữ liệu sinh trắc học.");
      return;
    }
    setBusy(true);
    try {
      const res = await api<AutoSession>(`/api/v1/employees/${employeeId}/enrollment/auto/start`, {
        method: "POST",
        body: JSON.stringify({
          authorization_ref: authRef,
          authorization_ack_vi:
            "Tôi xác nhận nhân viên đã được thông báo và đồng ý đăng ký khuôn mặt cho mục đích chấm công nội bộ.",
          source: "DEMO",
        }),
      });
      setSession(res);
      setFixtureKey(emps.find((x) => String(x.id) === employeeId)?.code || "DEMO");
      setMsg(res.message_vi || "Đã bắt đầu đăng ký tự động.");
      speakVi("Bắt đầu đăng ký. Nhìn thẳng vào camera.", soundOn);
      beep(soundOn);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function captureStep() {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      // DEMO path: distinct synthetic canvases via fixture key + step salt (not real camera)
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 640;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Không tạo được canvas DEMO");
      const step = session.current_step || "FACE_FRONT";
      ctx.fillStyle = `hsl(${(step.length * 37) % 360} 20% 45%)`;
      ctx.fillRect(0, 0, 640, 640);
      ctx.fillStyle = "#c4a484";
      ctx.fillRect(160, 40, 320, 560);
      const dataUrl = canvas.toDataURL("image/png");
      const image_base64 = dataUrl.split(",")[1];

      const res = await api<AutoSession & { quality?: unknown; body_quality?: unknown }>(
        `/api/v1/employees/${employeeId}/enrollment/auto/${session.session_id}/frame`,
        {
          method: "POST",
          body: JSON.stringify({
            identity_fixture_key: fixtureKey,
            image_base64,
            force_slot: step.startsWith("FACE_") || step.startsWith("BODY_") ? step : undefined,
          }),
        }
      );
      setSession(res);
      setLastQuality(res.quality || res.body_quality || null);
      if (res.accepted) {
        const ann = res.announcement_vi || res.message_vi || "Đã nhận mẫu.";
        setMsg(ann);
        speakVi(ann, soundOn);
        beep(soundOn);
      } else {
        setError(res.message_vi || STATE_HELP[res.ui_state] || "Chưa nhận mẫu");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function pauseResume(kind: "pause" | "resume") {
    if (!session) return;
    setBusy(true);
    try {
      const res = await api<AutoSession>(
        `/api/v1/employees/${employeeId}/enrollment/auto/${session.session_id}/${kind}`,
        { method: "POST", body: "{}" }
      );
      setSession(res);
      setMsg(res.guidance_vi);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function retrySlot() {
    if (!session) return;
    setBusy(true);
    try {
      const res = await api<AutoSession>(
        `/api/v1/employees/${employeeId}/enrollment/auto/${session.session_id}/retry-step`,
        {
          method: "POST",
          body: JSON.stringify({ slot: session.current_step }),
        }
      );
      setSession(res);
      setMsg("Đã mở lại bước hiện tại.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const res = await api<AutoSession & { activated?: boolean; message_vi?: string }>(
        `/api/v1/employees/${employeeId}/enrollment/auto/${session.session_id}/activate`,
        {
          method: "POST",
          body: JSON.stringify({ identity_fixture_key: fixtureKey }),
        }
      );
      setSession(res);
      setMsg(res.message_vi || (res.activated ? "Đã kích hoạt." : "Chưa kích hoạt."));
      if (res.activated) {
        speakVi("Đăng ký khuôn mặt đã được kích hoạt.", soundOn);
        beep(soundOn);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function cancelSession() {
    if (!session) return;
    setBusy(true);
    try {
      const res = await api<AutoSession>(
        `/api/v1/employees/${employeeId}/enrollment/auto/${session.session_id}/cancel`,
        { method: "POST", body: "{}" }
      );
      setSession(res);
      setMsg(res.guidance_vi || "Đã hủy phiên.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  function SlotTile({ slot }: { slot: string }) {
    const done = session?.completed_slots?.includes(slot);
    const current = session?.current_step === slot;
    return (
      <div
        className={`rounded-lg border px-3 py-2 text-sm ${
          done
            ? "border-ok/50 bg-ok/10 text-ok"
            : current
              ? "border-brand bg-brand/10 text-brand"
              : "border-line bg-canvas text-muted"
        }`}
      >
        <div className="font-medium">{done ? "✓ " : current ? "→ " : ""}{SLOT_LABEL[slot] || slot}</div>
        <div className="text-xs opacity-80">{slot}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Đăng ký khuôn mặt tự động</h1>
        <p className="text-sm text-muted mt-1">
          Quét toàn khung hình — không cần vẽ vùng ROI. Thu 3 tư thế mặt và 4 ảnh toàn thân tham chiếu.
          Nguồn DEMO không phải camera thật; CAMERA_LAB / FACE_PILOT vẫn bị chặn đến khi kiểm trên máy
          Windows công ty.{" "}
          <a className="text-brand underline" href="https://mypc.vn" target="_blank" rel="noreferrer">
            MyPC Viet Nam
          </a>
        </p>
      </header>

      {status && (
        <div className="rounded-xl border border-line bg-panel p-4 text-sm text-muted">
          {(status.note_vi as string) || JSON.stringify(status)}
        </div>
      )}

      <form onSubmit={startAuto} className="rounded-xl border border-line bg-panel p-4 space-y-3">
        <label className="block text-sm space-y-1">
          <span className="text-muted">Nhân viên</span>
          <select
            required
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
          >
            <option value="">— Chọn —</option>
            {emps.map((e) => (
              <option key={e.id} value={e.id}>
                {e.code} — {e.full_name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm space-y-1">
          <span className="text-muted">Mã ủy quyền / hồ sơ</span>
          <input
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={authRef}
            onChange={(e) => setAuthRef(e.target.value)}
            required
          />
        </label>
        <label className="flex gap-2 text-sm items-start">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>
            Đã thông báo cho nhân viên về việc xử lý dữ liệu sinh trắc học theo mục đích chấm công;
            có phương án thay thế không dùng khuôn mặt.
          </span>
        </label>
        <label className="flex gap-2 text-sm items-center">
          <input type="checkbox" checked={soundOn} onChange={(e) => setSoundOn(e.target.checked)} />
          <span>Âm báo / giọng nói tiếng Việt (nếu trình duyệt có giọng cục bộ)</span>
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-brand text-canvas font-medium px-4 py-2 disabled:opacity-50"
        >
          Bắt đầu đăng ký tự động (DEMO)
        </button>
      </form>

      {session && (
        <div className="rounded-xl border border-line bg-panel p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm">
              Phiên <span className="font-mono text-xs">{session.session_id.slice(0, 8)}</span> ·{" "}
              <span className="text-brand">{session.ui_state}</span>
            </div>
            <div className="text-sm text-muted">Tiến độ {progressPct}% · mặt {session.face_done}/3 · thân {session.body_done}/4</div>
          </div>
          <div className="h-2 rounded-full bg-canvas overflow-hidden border border-line">
            <div className="h-full bg-brand transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="text-sm">{session.guidance_vi || STATE_HELP[session.ui_state]}</p>
          <p className="text-xs text-muted">
            Bước hiện tại: <strong className="text-ink">{SLOT_LABEL[session.current_step] || session.current_step}</strong>
            {" · "}Không bắt buộc ROI ({session.roi_required === false ? "đã tắt" : "n/a"})
          </p>

          <div>
            <div className="text-xs text-muted mb-2">Tư thế khuôn mặt</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {FACE_SLOTS.map((s) => (
                <SlotTile key={s} slot={s} />
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted mb-2">Ảnh toàn thân tham chiếu (không phải sinh trắc học)</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {BODY_SLOTS.map((s) => (
                <SlotTile key={s} slot={s} />
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-dashed border-line bg-canvas/50 p-6 text-center text-sm text-muted">
            Vùng xem camera toàn khung (DEMO — không phải luồng REAL_CAMERA).
            <div className="mt-2 text-xs">Chế độ suy luận: {session.inference_mode || "—"}</div>
          </div>

          <label className="block text-sm space-y-1">
            <span className="text-muted">Khóa fixture kiểm thử (không phải ảnh nhân viên thật)</span>
            <input
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 font-mono"
              value={fixtureKey}
              onChange={(e) => setFixtureKey(e.target.value)}
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || session.status === "ACTIVE" || session.status === "CANCELLED"}
              onClick={captureStep}
              className="rounded-md bg-brand text-canvas px-3 py-2 text-sm disabled:opacity-50"
            >
              Thu mẫu bước hiện tại (DEMO)
            </button>
            <button type="button" disabled={busy} onClick={() => pauseResume("pause")} className="rounded-md border border-line px-3 py-2 text-sm">
              Tạm dừng
            </button>
            <button type="button" disabled={busy} onClick={() => pauseResume("resume")} className="rounded-md border border-line px-3 py-2 text-sm">
              Tiếp tục
            </button>
            <button type="button" disabled={busy} onClick={retrySlot} className="rounded-md border border-line px-3 py-2 text-sm">
              Thử lại bước
            </button>
            <button
              type="button"
              disabled={busy || (session.completed_slots || []).length < 7}
              onClick={activate}
              className="rounded-md bg-brand/15 border border-brand/40 text-brand px-3 py-2 text-sm disabled:opacity-50"
            >
              Xác minh & kích hoạt
            </button>
            <button type="button" disabled={busy} onClick={cancelSession} className="rounded-md border border-danger/40 text-danger px-3 py-2 text-sm">
              Hủy phiên
            </button>
            <button type="button" onClick={() => setShowQuality((v) => !v)} className="rounded-md border border-line px-3 py-2 text-sm text-muted">
              {showQuality ? "Ẩn" : "Xem"} chi tiết chất lượng
            </button>
          </div>
          {showQuality && lastQuality != null ? (
            <pre className="text-xs overflow-auto max-h-48 rounded-md bg-canvas border border-line p-2 text-muted">
              {JSON.stringify(lastQuality, null, 2)}
            </pre>
          ) : null}
        </div>
      )}

      {msg && (
        <div className="rounded-md border border-ok/40 bg-ok/10 text-ok px-3 py-2 text-sm">{msg}</div>
      )}
      {error && (
        <div className="rounded-md border border-danger/40 bg-danger/10 text-danger px-3 py-2 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

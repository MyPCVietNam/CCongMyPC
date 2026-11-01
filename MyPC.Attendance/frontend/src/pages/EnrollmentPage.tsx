import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Emp = { id: number; code: string; full_name: string; biometric_eligible: boolean };

export function EnrollmentPage() {
  const [emps, setEmps] = useState<Emp[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [ack, setAck] = useState(false);
  const [authRef, setAuthRef] = useState("HR-");
  const [enrollmentId, setEnrollmentId] = useState<number | null>(null);
  const [sampleCount, setSampleCount] = useState(0);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [fixtureKey, setFixtureKey] = useState("");

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

  async function start(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    if (!ack) {
      setError("Cần xác nhận thông báo xử lý dữ liệu sinh trắc học.");
      return;
    }
    try {
      const res = await api<{ enrollment_id: number; message_vi: string }>(
        `/api/v1/employees/${employeeId}/enrollment/start`,
        {
          method: "POST",
          body: JSON.stringify({
            employee_id: Number(employeeId),
            authorization_ref: authRef,
            authorization_ack_vi:
              "Tôi xác nhận nhân viên đã được thông báo và đồng ý đăng ký khuôn mặt cho mục đích chấm công nội bộ.",
            source: "DEMO",
          }),
        }
      );
      setEnrollmentId(res.enrollment_id);
      setSampleCount(0);
      setFixtureKey(emps.find((x) => String(x.id) === employeeId)?.code || "DEMO");
      setMsg(res.message_vi);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function addSample() {
    if (!enrollmentId) return;
    setError("");
    try {
      const res = await api<{
        accepted: boolean;
        message_vi: string;
        sample_count?: number;
        pixel_size?: number[];
      }>(`/api/v1/employees/${employeeId}/enrollment/${enrollmentId}/sample`, {
        method: "POST",
        body: JSON.stringify({ identity_fixture_key: fixtureKey }),
      });
      setMsg(
        res.message_vi +
          (res.pixel_size ? ` · kích thước khuôn mặt ~${res.pixel_size[0]} px` : "")
      );
      if (res.accepted && res.sample_count) setSampleCount(res.sample_count);
      if (!res.accepted) setError(res.message_vi);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function verify() {
    setError("");
    try {
      const res = await api<{ outcome: string; message_vi: string; employee_id?: number }>(
        "/api/v1/face/verify",
        {
          method: "POST",
          body: JSON.stringify({
            identity_fixture_key: fixtureKey,
            publish_attendance: true,
          }),
        }
      );
      setMsg(`${res.outcome}: ${res.message_vi}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Đăng ký khuôn mặt</h1>
        <p className="text-sm text-muted mt-1">
          Chỉ nhân viên được phê duyệt. Nguồn DEMO/fixture dùng cho kiểm thử — không ghi vào sổ
          production như camera thật. Zoom giao diện không làm tăng chi tiết ảnh gốc.
        </p>
      </header>

      {status && (
        <div className="rounded-xl border border-line bg-panel p-4 text-sm text-muted">
          Trạng thái model: {JSON.stringify(status.note_vi || status)}
        </div>
      )}

      <form onSubmit={start} className="rounded-xl border border-line bg-panel p-4 space-y-3">
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
        <button type="submit" className="rounded-md bg-brand text-canvas font-medium px-4 py-2">
          Bắt đầu đăng ký (DEMO)
        </button>
      </form>

      {enrollmentId && (
        <div className="rounded-xl border border-line bg-panel p-4 space-y-3">
          <div className="text-sm">
            Phiên đăng ký #{enrollmentId} · Số mẫu đạt:{" "}
            <span className="text-brand font-medium">{sampleCount}</span> / 5–10
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
              onClick={addSample}
              className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel2"
            >
              Thêm mẫu DEMO
            </button>
            <button
              type="button"
              onClick={verify}
              className="rounded-md bg-brand/15 border border-brand/40 text-brand px-3 py-2 text-sm"
            >
              Kiểm tra nhận diện
            </button>
          </div>
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

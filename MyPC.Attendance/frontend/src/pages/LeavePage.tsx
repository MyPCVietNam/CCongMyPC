import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Leave = {
  id: number;
  employee_id: number;
  kind: string;
  work_date: string;
  status: string;
  reason: string;
};

type Emp = { id: number; code: string; full_name: string };

const KIND_VI: Record<string, string> = {
  FULL_DAY: "Cả ngày",
  MORNING: "Buổi sáng",
  AFTERNOON: "Buổi chiều",
  HOURLY: "Theo giờ",
  OFFSITE: "Công tác ngoài",
};

export function LeavePage() {
  const [rows, setRows] = useState<Leave[]>([]);
  const [emps, setEmps] = useState<Emp[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    employee_id: "",
    kind: "AFTERNOON",
    work_date: new Date().toISOString().slice(0, 10),
    reason: "",
  });

  async function reload() {
    const [l, e] = await Promise.all([
      api<Leave[]>("/api/v1/leave"),
      api<Emp[]>("/api/v1/employees"),
    ]);
    setRows(l);
    setEmps(e);
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/v1/leave", {
        method: "POST",
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          kind: form.kind,
          work_date: form.work_date,
          reason: form.reason,
        }),
      });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  async function approve(id: number) {
    setError("");
    try {
      await api(`/api/v1/leave/${id}/approve`, { method: "POST" });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Đơn nghỉ & Công tác</h1>
        <p className="text-sm text-muted mt-1">
          Chỉ người phụ trách tính công được xác nhận. SYSTEM_ADMIN không tự có quyền phê duyệt.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="rounded-xl border border-line bg-panel p-4 grid sm:grid-cols-2 lg:grid-cols-5 gap-3"
      >
        <label className="text-sm space-y-1">
          <span className="text-muted">Nhân viên</span>
          <select
            required
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={form.employee_id}
            onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
          >
            <option value="">— Chọn —</option>
            {emps.map((e) => (
              <option key={e.id} value={e.id}>
                {e.code} — {e.full_name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm space-y-1">
          <span className="text-muted">Loại</span>
          <select
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
          >
            {Object.entries(KIND_VI).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm space-y-1">
          <span className="text-muted">Ngày</span>
          <input
            type="date"
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={form.work_date}
            onChange={(e) => setForm({ ...form, work_date: e.target.value })}
          />
        </label>
        <label className="text-sm space-y-1 lg:col-span-1">
          <span className="text-muted">Lý do</span>
          <input
            className="w-full rounded-md bg-canvas border border-line px-3 py-2"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded-md bg-brand text-canvas font-medium py-2"
          >
            Gửi đơn
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-md border border-danger/40 bg-danger/10 text-danger px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-panel2 text-muted text-left">
            <tr>
              <th className="px-3 py-3">ID</th>
              <th className="px-3 py-3">NV</th>
              <th className="px-3 py-3">Loại</th>
              <th className="px-3 py-3">Ngày</th>
              <th className="px-3 py-3">Trạng thái</th>
              <th className="px-3 py-3">Thao tác</th>
            </tr>
          </thead>
          <tbody className="bg-panel">
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="px-3 py-3">{r.id}</td>
                <td className="px-3 py-3">{r.employee_id}</td>
                <td className="px-3 py-3">{KIND_VI[r.kind] || r.kind}</td>
                <td className="px-3 py-3">{r.work_date.split("-").reverse().join("/")}</td>
                <td className="px-3 py-3">{r.status}</td>
                <td className="px-3 py-3">
                  {r.status === "PENDING_APPROVAL" && (
                    <button
                      type="button"
                      onClick={() => approve(r.id)}
                      className="text-brand hover:underline"
                    >
                      Phê duyệt
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

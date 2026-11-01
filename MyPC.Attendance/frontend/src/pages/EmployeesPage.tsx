import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";

type Emp = {
  id: number;
  code: string;
  full_name: string;
  department: string;
  job_title: string;
  active: boolean;
  shift_id: string;
  biometric_eligible: boolean;
};

export function EmployeesPage() {
  const [rows, setRows] = useState<Emp[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    code: "",
    full_name: "",
    department: "",
    job_title: "",
  });

  async function reload() {
    const list = await api<Emp[]>("/api/v1/employees");
    setRows(list);
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/v1/employees", {
        method: "POST",
        body: JSON.stringify({ ...form, active: true, shift_id: "MYPC-ADMIN-01" }),
      });
      setForm({ code: "", full_name: "", department: "", job_title: "" });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Nhân viên</h1>
        <p className="text-sm text-muted mt-1">
          Đăng ký khuôn mặt có kiểm soát sẽ mở ở P01 — P00 quản lý hồ sơ cơ bản.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="rounded-xl border border-line bg-panel p-4 grid sm:grid-cols-2 lg:grid-cols-5 gap-3"
      >
        <Field label="Mã" value={form.code} onChange={(v) => setForm({ ...form, code: v })} />
        <Field
          label="Họ và tên"
          value={form.full_name}
          onChange={(v) => setForm({ ...form, full_name: v })}
        />
        <Field
          label="Phòng ban"
          value={form.department}
          onChange={(v) => setForm({ ...form, department: v })}
        />
        <Field
          label="Chức danh"
          value={form.job_title}
          onChange={(v) => setForm({ ...form, job_title: v })}
        />
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded-md bg-brand text-canvas font-medium py-2 hover:brightness-110"
          >
            Thêm nhân viên
          </button>
        </div>
      </form>

      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-panel2 text-muted text-left">
            <tr>
              <th className="px-3 py-3">Mã</th>
              <th className="px-3 py-3">Họ tên</th>
              <th className="px-3 py-3">Phòng</th>
              <th className="px-3 py-3">Ca</th>
              <th className="px-3 py-3">Sinh trắc</th>
            </tr>
          </thead>
          <tbody className="bg-panel">
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="px-3 py-3">{r.code}</td>
                <td className="px-3 py-3">{r.full_name}</td>
                <td className="px-3 py-3">{r.department || "—"}</td>
                <td className="px-3 py-3">{r.shift_id}</td>
                <td className="px-3 py-3">
                  {r.biometric_eligible ? "Được phép" : "Chưa đăng ký"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
        required={label === "Mã" || label === "Họ và tên"}
        className="w-full rounded-md bg-canvas border border-line px-3 py-2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

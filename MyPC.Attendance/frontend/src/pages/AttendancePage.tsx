import { useEffect, useState } from "react";
import { api } from "../api/client";
import { vi } from "../i18n/vi";

type Daily = {
  work_date: string;
  labels_vi: Record<string, string>;
  rows: Array<{
    employee_id: number;
    code: string;
    full_name: string;
    department: string;
    morning: { observed_at_utc: string | null; status: string; late_seconds: number; note_vi: string } | null;
    afternoon: {
      afternoon_reference_observed_at: string | null;
      afternoon_first_observed_at: string | null;
      afternoon_primary_photo_captured_at: string | null;
      selection_status: string;
      note_vi: string;
      review_required: boolean;
    } | null;
  }>;
};

export function AttendancePage() {
  const [workDate, setWorkDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<Daily | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    setError("");
    api<Daily>(`/api/v1/attendance/daily?work_date=${workDate}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [workDate]);

  const rows =
    data?.rows.filter(
      (r) =>
        !q ||
        r.full_name.toLowerCase().includes(q.toLowerCase()) ||
        r.code.toLowerCase().includes(q.toLowerCase()) ||
        r.department.toLowerCase().includes(q.toLowerCase())
    ) || [];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end gap-3 justify-between">
        <div>
          <h1 className="text-2xl font-display">Chấm công</h1>
          <p className="text-sm text-muted mt-1">
            Phân biệt {vi.labels.afternoonRef}, {vi.labels.firstPm}, {vi.labels.photoAt},{" "}
            {vi.labels.shiftEndAnchor}
          </p>
        </div>
        <div className="flex gap-2">
          <input
            type="date"
            value={workDate}
            onChange={(e) => setWorkDate(e.target.value)}
            className="rounded-md bg-panel border border-line px-3 py-2 text-sm"
          />
          <input
            placeholder="Tìm theo tên / mã / phòng"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="rounded-md bg-panel border border-line px-3 py-2 text-sm min-w-[220px]"
          />
        </div>
      </header>

      {error && <div className="text-danger text-sm">{error}</div>}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-panel2 text-muted text-left">
            <tr>
              <th className="px-3 py-3 font-medium">Mã</th>
              <th className="px-3 py-3 font-medium">Họ tên</th>
              <th className="px-3 py-3 font-medium">Sáng</th>
              <th className="px-3 py-3 font-medium">{vi.labels.firstPm}</th>
              <th className="px-3 py-3 font-medium">{vi.labels.afternoonRef}</th>
              <th className="px-3 py-3 font-medium">{vi.labels.photoAt}</th>
              <th className="px-3 py-3 font-medium">{vi.labels.shiftEndAnchor}</th>
              <th className="px-3 py-3 font-medium">Trạng thái</th>
            </tr>
          </thead>
          <tbody className="bg-panel">
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted">
                  Chưa có dữ liệu nhân viên cho ngày này
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.employee_id} className="border-t border-line">
                <td className="px-3 py-3">{r.code}</td>
                <td className="px-3 py-3">
                  <div>{r.full_name}</div>
                  <div className="text-xs text-muted">{r.department}</div>
                </td>
                <td className="px-3 py-3">{fmt(r.morning?.observed_at_utc)}</td>
                <td className="px-3 py-3">{fmt(r.afternoon?.afternoon_first_observed_at)}</td>
                <td className="px-3 py-3 font-medium text-brand">
                  {fmt(r.afternoon?.afternoon_reference_observed_at)}
                </td>
                <td className="px-3 py-3">{fmt(r.afternoon?.afternoon_primary_photo_captured_at)}</td>
                <td className="px-3 py-3 text-muted">18:00</td>
                <td className="px-3 py-3">
                  {r.afternoon?.review_required ? (
                    <span className="text-warn">Cần đối soát</span>
                  ) : (
                    r.afternoon?.note_vi || r.morning?.note_vi || "—"
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

function fmt(iso?: string | null) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZone: "Asia/Ho_Chi_Minh",
    });
  } catch {
    return iso;
  }
}

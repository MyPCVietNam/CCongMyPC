import { useEffect, useState } from "react";
import { api } from "../api/client";

type Overview = {
  work_date: string;
  camera_status_vi: string;
  camera_note_vi: string;
  total_staff: number;
  morning_present: number;
  morning_late: number;
  afternoon_present: number;
  overtime: { active: number; confirmed: number; needs_review: number; note_vi: string };
  config_version: number;
  mock_indicator_vi: string | null;
  afternoon_window: { start: string; end_exclusive: string; reference: string };
  exit_verification_gate: string;
};

export function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>("/api/v1/overview")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorBox msg={error} />;
  if (!data) return <p className="text-muted">Đang tải tổng quan…</p>;

  const morningMissing = Math.max(0, data.total_staff - data.morning_present);
  const afternoonMissing = Math.max(0, data.total_staff - data.afternoon_present);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-display tracking-tight">Tổng quan</h1>
        <p className="text-muted text-sm">
          Ngày làm việc {formatDate(data.work_date)} · Cấu hình v{data.config_version}
          {data.mock_indicator_vi ? ` · ${data.mock_indicator_vi}` : ""}
        </p>
      </header>

      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Camera" value={data.camera_status_vi} hint={data.camera_note_vi} />
        <Stat label="Tổng nhân viên" value={String(data.total_staff)} />
        <Stat
          label="Sáng (có mặt / muộn / thiếu)"
          value={`${data.morning_present} / ${data.morning_late} / ${morningMissing}`}
        />
        <Stat
          label="Chiều (có điểm danh / thiếu)"
          value={`${data.afternoon_present} / ${afternoonMissing}`}
        />
      </section>

      <section className="grid lg:grid-cols-2 gap-4">
        <Panel title="Tăng ca">
          <ul className="space-y-2 text-sm">
            <li>Đang tăng ca: {data.overtime.active}</li>
            <li>Đã xác nhận: {data.overtime.confirmed}</li>
            <li>Cần đối soát: {data.overtime.needs_review}</li>
            <li className="text-muted">{data.overtime.note_vi}</li>
          </ul>
        </Panel>
        <Panel title="Cửa sổ nhận diện chiều (v1.5)">
          <ul className="space-y-2 text-sm">
            <li>
              Khoảng nhận diện: [{data.afternoon_window.start},{" "}
              {data.afternoon_window.end_exclusive}) — hết phút 23:55
            </li>
            <li>Mốc tham chiếu chọn mẫu: {data.afternoon_window.reference}</li>
            <li>
              Cổng xác minh ra về:{" "}
              <span className="text-warn">{data.exit_verification_gate}</span>
            </li>
            <li className="text-muted">
              18:00 là mốc chọn mẫu, không phải giờ bịa đặt quan sát.
            </li>
          </ul>
        </Panel>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2 text-lg font-medium">{value}</div>
      {hint && <div className="mt-2 text-xs text-muted">{hint}</div>}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium mb-3">{title}</h2>
      {children}
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="rounded-md border border-danger/40 bg-danger/10 text-danger px-4 py-3">
      {msg}
    </div>
  );
}

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

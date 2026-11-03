import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { vi } from "../i18n/vi";

type SettingsResp = {
  config: {
    version: number;
    shift_id: string;
    windows: {
      afternoon_recognition_start: string;
      afternoon_recognition_end_exclusive: string;
      morning_recognition_start: string;
      morning_recognition_end: string;
      shift_start: string;
      shift_end: string;
      lunch_start: string;
      lunch_end: string;
      afternoon_selection: {
        reference_time: string;
        near_tolerance_before_minutes: number;
        near_tolerance_after_minutes: number;
        preferred_photo_start: string;
        preferred_photo_end: string;
      };
    };
    exit_verification_gate: string;
    mock_camera_enabled: boolean;
  };
  impact_preview_vi: string;
  ack_at: string | null;
};

export function SettingsPage() {
  const [data, setData] = useState<SettingsResp | null>(null);
  const [draft, setDraft] = useState<SettingsResp["config"] | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function reload() {
    const s = await api<SettingsResp>("/api/v1/settings");
    setData(s);
    setDraft(structuredClone(s.config));
  }

  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);

  async function apply() {
    if (!draft || !data) return;
    setError("");
    setMsg("");
    try {
      const res = await api<{
        applied: boolean;
        message_vi: string;
        ui_status_vi: string;
      }>("/api/v1/settings/apply", {
        method: "POST",
        body: JSON.stringify({
          expected_version: data.config.version,
          config: draft,
          reason: "Áp dụng từ giao diện",
        }),
      });
      setMsg(`${res.ui_status_vi}: ${res.message_vi}`);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  if (!draft) return <p className="text-muted">Đang tải cấu hình…</p>;

  const w = draft.windows;
  const sel = w.afternoon_selection;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-display">Cài đặt</h1>
        <p className="text-sm text-muted mt-1">
          Phiên bản đang chạy: v{data?.config.version}. {data?.impact_preview_vi}
        </p>
      </header>

      <section className="rounded-xl border border-line bg-panel p-5 space-y-4">
        <h2 className="font-medium">Ca làm việc & cửa sổ nhận diện</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <TimeField
            label="Giờ bắt đầu ca"
            value={w.shift_start}
            onChange={(v) => setDraft({ ...draft, windows: { ...w, shift_start: v } })}
          />
          <TimeField
            label="Giờ kết thúc ca / mốc OT"
            value={w.shift_end}
            onChange={(v) => setDraft({ ...draft, windows: { ...w, shift_end: v } })}
          />
          <TimeField
            label="Nghỉ trưa bắt đầu"
            value={w.lunch_start}
            onChange={(v) => setDraft({ ...draft, windows: { ...w, lunch_start: v } })}
          />
          <TimeField
            label="Nghỉ trưa kết thúc"
            value={w.lunch_end}
            onChange={(v) => setDraft({ ...draft, windows: { ...w, lunch_end: v } })}
          />
          <TimeField
            label="Nhận diện sáng từ"
            value={w.morning_recognition_start}
            onChange={(v) =>
              setDraft({ ...draft, windows: { ...w, morning_recognition_start: v } })
            }
          />
          <TimeField
            label="Nhận diện sáng đến (gồm giây)"
            value={w.morning_recognition_end}
            onChange={(v) =>
              setDraft({ ...draft, windows: { ...w, morning_recognition_end: v } })
            }
          />
          <TimeField
            label="Nhận diện chiều từ"
            value={w.afternoon_recognition_start}
            onChange={(v) =>
              setDraft({ ...draft, windows: { ...w, afternoon_recognition_start: v } })
            }
          />
          <TimeField
            label="Nhận diện chiều đến (exclusive, mặc định 23:56:00)"
            value={w.afternoon_recognition_end_exclusive}
            onChange={(v) =>
              setDraft({
                ...draft,
                windows: { ...w, afternoon_recognition_end_exclusive: v },
              })
            }
          />
          <TimeField
            label="Mốc tham chiếu chiều (không bịa timestamp)"
            value={sel.reference_time}
            onChange={(v) =>
              setDraft({
                ...draft,
                windows: {
                  ...w,
                  afternoon_selection: { ...sel, reference_time: v },
                },
              })
            }
          />
          <TimeField
            label="Ảnh ưu tiên từ"
            value={sel.preferred_photo_start}
            onChange={(v) =>
              setDraft({
                ...draft,
                windows: {
                  ...w,
                  afternoon_selection: { ...sel, preferred_photo_start: v },
                },
              })
            }
          />
          <TimeField
            label="Ảnh ưu tiên đến"
            value={sel.preferred_photo_end}
            onChange={(v) =>
              setDraft({
                ...draft,
                windows: {
                  ...w,
                  afternoon_selection: { ...sel, preferred_photo_end: v },
                },
              })
            }
          />
        </div>
        <p className="text-xs text-muted">
          v1.5: cửa sổ chiều gồm hết phút 23:55 ([17:00, 23:56)). Không dùng cutoff 19:00.
        </p>
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={apply}
          className="rounded-md bg-brand text-canvas font-medium px-4 py-2"
        >
          {vi.labels.apply}
        </button>
        <button
          type="button"
          onClick={() => data && setDraft(structuredClone(data.config))}
          className="rounded-md border border-line px-4 py-2 text-sm"
        >
          {vi.labels.revert}
        </button>
      </div>

      {msg && (
        <div className="rounded-md border border-ok/40 bg-ok/10 text-ok px-3 py-2 text-sm">
          {msg}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-danger/40 bg-danger/10 text-danger px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <details className="rounded-xl border border-line bg-panel p-5">
        <summary className="cursor-pointer font-medium">Phần quản trị (Windows Lab · Nhật ký)</summary>
        <div className="mt-3 space-y-3 text-sm">
          <p className="text-muted">
            Các công cụ chẩn đoán và lab vật lý chỉ dành cho quản trị viên. API vẫn kiểm tra quyền.
            Cổng CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER giữ BLOCKED đến khi có bằng
            chứng Windows thật từ owner.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/lab-windows"
              className="rounded-md border border-line px-3 py-2 hover:bg-panel2 transition"
            >
              Windows Lab (wizard)
            </Link>
            <Link
              to="/nhat-ky"
              className="rounded-md border border-line px-3 py-2 hover:bg-panel2 transition"
            >
              Nhật ký & chẩn đoán
            </Link>
            <Link
              to="/camera"
              className="rounded-md border border-line px-3 py-2 hover:bg-panel2 transition"
            >
              Camera LIVE
            </Link>
          </div>
          <p className="text-xs text-muted">
            mock_camera_enabled (cấu hình ứng dụng) = {String(draft.mock_camera_enabled)} — khác với
            trạng thái LIVE từng camera.
          </p>
        </div>
      </details>
    </div>
  );
}

function TimeField({
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
        className="w-full rounded-md bg-canvas border border-line px-3 py-2 font-mono"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        pattern="\d{2}:\d{2}:\d{2}"
      />
    </label>
  );
}

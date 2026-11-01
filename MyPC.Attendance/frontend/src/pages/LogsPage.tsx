import { useEffect, useState } from "react";
import { api } from "../api/client";

type Diag = {
  app: string;
  app_version: string;
  spec_version: string;
  schema_version: number;
  config_version: number;
  sqlite_integrity: string;
  camera: Record<string, unknown>;
  gates: Record<string, unknown>;
  afternoon_window: Record<string, string>;
  ai_models: Record<string, string>;
};

export function LogsPage() {
  const [diag, setDiag] = useState<Diag | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Diag>("/api/v1/system/diagnostics")
      .then(setDiag)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-display">Nhật ký & Sức khỏe hệ thống</h1>
      {error && <div className="text-danger text-sm">{error}</div>}
      {!diag && !error && <p className="text-muted">Đang tải…</p>}
      {diag && (
        <pre className="rounded-xl border border-line bg-panel p-4 text-xs overflow-auto scrollbar-thin leading-relaxed">
          {JSON.stringify(diag, null, 2)}
        </pre>
      )}
    </div>
  );
}

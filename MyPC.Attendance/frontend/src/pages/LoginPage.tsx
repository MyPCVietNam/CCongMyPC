import { FormEvent, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api, setCsrfToken } from "../api/client";
import { vi } from "../i18n/vi";

type User = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  must_change_password?: boolean;
  data_dir_hint?: string;
};

export function LoginPage({
  onLoggedIn,
}: {
  onLoggedIn: (user: User, csrf: string) => void;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{
        user: User;
        csrf_token: string;
        must_change_password?: boolean;
        data_dir_hint?: string;
      }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setCsrfToken(res.csrf_token);
      onLoggedIn(
        {
          ...res.user,
          must_change_password:
            res.user.must_change_password ?? res.must_change_password,
          data_dir_hint: res.data_dir_hint,
        },
        res.csrf_token
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-md animate-fade-up">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 h-14 w-14 rounded-xl bg-brand/15 border border-brand/40 grid place-items-center text-brand text-2xl font-semibold">
            M
          </div>
          <h1 className="font-display text-3xl tracking-tight">{vi.brand}</h1>
          <p className="mt-2 text-muted text-sm">
            Chấm công offline-first · Camera EZVIZ · Đặc tả v1.5
          </p>
        </div>
        <form
          onSubmit={submit}
          className="rounded-xl border border-line bg-panel p-6 shadow-soft space-y-4"
        >
          <h2 className="text-lg font-medium">{vi.login.title}</h2>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">{vi.login.username}</span>
            <input
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 outline-none focus:border-brand"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">{vi.login.password}</span>
            <input
              type="password"
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 outline-none focus:border-brand"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && (
            <div className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-brand text-canvas font-medium py-2.5 hover:brightness-110 disabled:opacity-60 transition"
          >
            {busy ? "Đang xử lý…" : vi.login.submit}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          <a
            href={vi.footerUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 hover:text-brand"
          >
            {vi.footer}
            <ExternalLink size={14} />
          </a>
        </p>
      </div>
    </div>
  );
}

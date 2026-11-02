import { FormEvent, useState } from "react";
import { api } from "../api/client";

export function ChangePasswordPage({
  username,
  dataDirHint,
  onChanged,
  onLogout,
}: {
  username: string;
  dataDirHint?: string;
  onChanged: () => void;
  onLogout: () => void;
}) {
  const [currentPassword, setCurrent] = useState("");
  const [newPassword, setNew] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (newPassword.length < 10) {
      setError("Mật khẩu mới phải có ít nhất 10 ký tự.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Xác nhận mật khẩu không khớp.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("Mật khẩu mới phải khác mật khẩu hiện tại.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      onChanged();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Đổi mật khẩu thất bại. 401 nghĩa là mật khẩu hiện tại bị từ chối — chưa áp dụng mật khẩu mới."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-md animate-fade-up">
        <div className="mb-6 text-center">
          <h1 className="font-display text-2xl tracking-tight">Đổi mật khẩu bắt buộc</h1>
          <p className="mt-2 text-sm text-muted">
            Tài khoản <strong>{username}</strong> phải đổi mật khẩu trước khi dùng dashboard /
            camera / lab.
          </p>
          {dataDirHint ? (
            <p className="mt-2 text-xs text-muted break-all">
              Hồ sơ dữ liệu đang dùng: {dataDirHint}
            </p>
          ) : null}
        </div>
        <form
          onSubmit={submit}
          className="rounded-xl border border-line bg-panel p-6 shadow-soft space-y-4"
          autoComplete="on"
        >
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">Mật khẩu hiện tại</span>
            <input
              type="password"
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 outline-none focus:border-brand"
              value={currentPassword}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">Mật khẩu mới (≥ 10 ký tự)</span>
            <input
              type="password"
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 outline-none focus:border-brand"
              value={newPassword}
              onChange={(e) => setNew(e.target.value)}
              autoComplete="new-password"
              minLength={10}
              required
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted">Xác nhận mật khẩu mới</span>
            <input
              type="password"
              className="w-full rounded-md bg-canvas border border-line px-3 py-2 outline-none focus:border-brand"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              minLength={10}
              required
            />
          </label>
          {error ? (
            <div className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-md px-3 py-2">
              {error}
            </div>
          ) : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-brand text-canvas font-medium py-2.5 hover:brightness-110 disabled:opacity-60 transition"
          >
            {busy ? "Đang lưu…" : "Đổi mật khẩu và đăng nhập lại"}
          </button>
          <button
            type="button"
            onClick={onLogout}
            className="w-full rounded-md border border-line py-2 text-sm text-muted hover:bg-panel2"
          >
            Đăng xuất
          </button>
        </form>
        <p className="mt-4 text-xs text-muted text-center">
          Mật khẩu lần đầu gắn với đúng thư mục dữ liệu (ProgramData / LocalAppData / MYPC_DATA_DIR).
          Không dán mật khẩu vào PowerShell.
        </p>
      </div>
    </div>
  );
}

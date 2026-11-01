import { ExternalLink, LogOut } from "lucide-react";
import { NavLink } from "react-router-dom";
import { ReactNode } from "react";
import { vi } from "../i18n/vi";

const links = [
  { to: "/", label: vi.nav.overview },
  { to: "/cham-cong", label: vi.nav.attendance },
  { to: "/tang-ca", label: vi.nav.overtime },
  { to: "/nhan-vien", label: vi.nav.employees },
  { to: "/dang-ky-khuon-mat", label: "Đăng ký khuôn mặt" },
  { to: "/don-nghi", label: vi.nav.leave },
  { to: "/bao-cao", label: vi.nav.reports },
  { to: "/camera", label: vi.nav.camera },
  { to: "/cai-dat", label: vi.nav.settings },
  { to: "/nhat-ky", label: vi.nav.logs },
];

export function Layout({
  user,
  onLogout,
  children,
}: {
  user: { display_name: string; username: string; role: string };
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line bg-panel/90 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-md bg-brand/15 border border-brand/40 grid place-items-center text-brand font-semibold">
              M
            </div>
            <div className="min-w-0">
              <div className="font-display text-lg tracking-tight text-ink truncate">
                {vi.brand}
              </div>
              <div className="text-xs text-muted flex items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
                  {vi.mock}
                </span>
                <span>· đặc tả v1.5</span>
              </div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3 text-sm text-muted">
            <span className="hidden sm:inline">
              {user.display_name || user.username} ({user.role})
            </span>
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 hover:bg-panel2 transition"
            >
              <LogOut size={14} />
              Đăng xuất
            </button>
          </div>
        </div>
        <nav className="max-w-7xl mx-auto px-2 pb-2 overflow-x-auto scrollbar-thin">
          <ul className="flex gap-1 min-w-max">
            {links.map((l) => (
              <li key={l.to}>
                <NavLink
                  to={l.to}
                  end={l.to === "/"}
                  className={({ isActive }) =>
                    `block px-3 py-2 rounded-md text-sm transition ${
                      isActive
                        ? "bg-brand/15 text-brand border border-brand/30"
                        : "text-muted hover:text-ink hover:bg-panel2"
                    }`
                  }
                >
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 animate-fade-up">
        {children}
      </main>

      <footer className="border-t border-line py-4 text-center text-sm text-muted">
        <a
          href={vi.footerUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 hover:text-brand transition"
        >
          {vi.footer}
          <ExternalLink size={14} aria-hidden />
        </a>
      </footer>
    </div>
  );
}

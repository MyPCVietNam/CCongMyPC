import { ChevronDown, ExternalLink, LogOut, Menu, X } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { ReactNode, useMemo, useState } from "react";
import { vi } from "../i18n/vi";

type NavChild = { to: string; label: string; adminOnly?: boolean };
type NavGroup = {
  id: string;
  label: string;
  to?: string;
  children?: NavChild[];
};

const groups: NavGroup[] = [
  { id: "overview", label: "Tổng quan", to: "/" },
  {
    id: "attendance",
    label: "Chấm công",
    to: "/cham-cong",
    children: [
      { to: "/cham-cong", label: "Bảng chấm công" },
      { to: "/tang-ca", label: "Theo dõi tăng ca" },
      { to: "/don-nghi", label: "Đơn nghỉ & Công tác" },
    ],
  },
  {
    id: "employees",
    label: "Nhân viên",
    to: "/nhan-vien",
    children: [
      { to: "/nhan-vien", label: "Danh sách nhân viên" },
      { to: "/dang-ky-khuon-mat", label: "Đăng ký khuôn mặt" },
    ],
  },
  { id: "camera", label: "Camera", to: "/camera" },
  { id: "reports", label: "Báo cáo", to: "/bao-cao" },
  {
    id: "settings",
    label: "Cài đặt",
    to: "/cai-dat",
    children: [
      { to: "/cai-dat", label: "Cấu hình vận hành" },
      { to: "/lab-windows", label: "Windows Lab", adminOnly: true },
      { to: "/nhat-ky", label: "Nhật ký & chẩn đoán", adminOnly: true },
    ],
  },
];

function pathInGroup(pathname: string, g: NavGroup): boolean {
  if (g.to && (pathname === g.to || (g.to !== "/" && pathname.startsWith(g.to)))) return true;
  return Boolean(g.children?.some((c) => pathname === c.to || pathname.startsWith(c.to + "/")));
}

export function Layout({
  user,
  onLogout,
  children,
  provenanceLabel,
}: {
  user: { display_name: string; username: string; role: string };
  onLogout: () => void;
  children: ReactNode;
  provenanceLabel?: string;
}) {
  const location = useLocation();
  // Admin nav hints only — API still enforces RBAC on each route.
  const isAdmin = ["SYSTEM_ADMIN", "admin", "ADMIN", "owner", "OWNER", "Administrator"].includes(
    user.role
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const activeGroup = useMemo(
    () => groups.find((g) => pathInGroup(location.pathname, g))?.id ?? null,
    [location.pathname]
  );

  const subLinks = useMemo(() => {
    const g = groups.find((x) => x.id === (openGroup || activeGroup));
    return (g?.children || []).filter((c) => !c.adminOnly || isAdmin);
  }, [openGroup, activeGroup, isAdmin]);

  return (
    <div className="min-h-screen flex flex-col bg-canvas">
      <header className="border-b border-line bg-panel/95 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-3 sm:px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            className="sm:hidden rounded-md border border-line p-2 text-muted"
            aria-label={mobileOpen ? "Đóng menu" : "Mở menu"}
            onClick={() => setMobileOpen((v) => !v)}
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-md bg-brand/15 border border-brand/40 grid place-items-center text-brand font-semibold">
              M
            </div>
            <div className="min-w-0">
              <div className="font-display text-lg tracking-tight text-ink truncate">{vi.brand}</div>
              <div className="text-xs text-muted flex items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
                  {provenanceLabel || "Nguồn chưa xác minh"}
                </span>
              </div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3 text-sm text-muted">
            <span className="hidden md:inline truncate max-w-[12rem]">
              {user.display_name || user.username} ({user.role})
            </span>
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 hover:bg-panel2 transition"
            >
              <LogOut size={14} />
              <span className="hidden sm:inline">Đăng xuất</span>
            </button>
          </div>
        </div>

        {/* Desktop primary 6 groups */}
        <nav className="hidden sm:block max-w-7xl mx-auto px-2 pb-2" aria-label="Điều hướng chính">
          <ul className="flex gap-1 flex-wrap">
            {groups.map((g) => {
              const active = pathInGroup(location.pathname, g);
              const hasChildren = Boolean(g.children?.length);
              return (
                <li key={g.id} className="relative">
                  {hasChildren ? (
                    <button
                      type="button"
                      className={`inline-flex items-center gap-1 px-3 py-2 rounded-md text-sm transition ${
                        active
                          ? "bg-brand/15 text-brand border border-brand/30"
                          : "text-muted hover:text-ink hover:bg-panel2"
                      }`}
                      aria-expanded={openGroup === g.id}
                      onClick={() => setOpenGroup((cur) => (cur === g.id ? null : g.id))}
                    >
                      {g.label}
                      <ChevronDown size={14} />
                    </button>
                  ) : (
                    <NavLink
                      to={g.to || "/"}
                      end={g.to === "/"}
                      className={({ isActive }) =>
                        `block px-3 py-2 rounded-md text-sm transition ${
                          isActive
                            ? "bg-brand/15 text-brand border border-brand/30"
                            : "text-muted hover:text-ink hover:bg-panel2"
                        }`
                      }
                    >
                      {g.label}
                    </NavLink>
                  )}
                </li>
              );
            })}
          </ul>
          {subLinks.length > 0 ? (
            <ul className="flex gap-1 mt-1 pl-1 overflow-x-auto">
              {subLinks.map((c) => (
                <li key={c.to}>
                  <NavLink
                    to={c.to}
                    end
                    onClick={() => setOpenGroup(null)}
                    className={({ isActive }) =>
                      `block px-2.5 py-1.5 rounded text-xs transition ${
                        isActive ? "bg-panel2 text-ink border border-line" : "text-muted hover:text-ink"
                      }`
                    }
                  >
                    {c.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          ) : null}
        </nav>

        {/* Mobile drawer */}
        {mobileOpen ? (
          <nav className="sm:hidden border-t border-line bg-panel px-3 py-3 space-y-2" aria-label="Menu mobile">
            {groups.map((g) => (
              <div key={g.id} className="space-y-1">
                {g.children?.length ? (
                  <>
                    <div className="text-xs uppercase tracking-wide text-muted px-1">{g.label}</div>
                    {g.children
                      .filter((c) => !c.adminOnly || isAdmin)
                      .map((c) => (
                        <NavLink
                          key={c.to}
                          to={c.to}
                          end
                          onClick={() => setMobileOpen(false)}
                          className={({ isActive }) =>
                            `block rounded-md px-3 py-2 text-sm ${
                              isActive ? "bg-brand/15 text-brand" : "text-ink hover:bg-panel2"
                            }`
                          }
                        >
                          {c.label}
                        </NavLink>
                      ))}
                  </>
                ) : (
                  <NavLink
                    to={g.to || "/"}
                    end={g.to === "/"}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      `block rounded-md px-3 py-2 text-sm ${
                        isActive ? "bg-brand/15 text-brand" : "text-ink hover:bg-panel2"
                      }`
                    }
                  >
                    {g.label}
                  </NavLink>
                )}
              </div>
            ))}
          </nav>
        ) : null}
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-4 py-5 sm:py-6 animate-fade-up">
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

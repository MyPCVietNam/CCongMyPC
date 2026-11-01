import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, setCsrfToken } from "./api/client";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { AttendancePage } from "./pages/AttendancePage";
import { OvertimePage } from "./pages/OvertimePage";
import { EmployeesPage } from "./pages/EmployeesPage";
import { LeavePage } from "./pages/LeavePage";
import { ReportsPage } from "./pages/ReportsPage";
import { CameraPage } from "./pages/CameraPage";
import { SettingsPage } from "./pages/SettingsPage";
import { LogsPage } from "./pages/LogsPage";
import { EnrollmentPage } from "./pages/EnrollmentPage";

type User = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  csrf_token?: string;
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<User>("/api/v1/auth/me")
      .then((u) => {
        if (u.csrf_token) setCsrfToken(u.csrf_token);
        setUser(u);
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center text-muted">
        Đang tải…
      </div>
    );
  }

  if (!user) {
    return (
      <LoginPage
        onLoggedIn={(u, csrf) => {
          setCsrfToken(csrf);
          setUser(u);
        }}
      />
    );
  }

  return (
    <Layout
      user={user}
      onLogout={async () => {
        await api("/api/v1/auth/logout", { method: "POST" });
        setUser(null);
      }}
    >
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/cham-cong" element={<AttendancePage />} />
        <Route path="/tang-ca" element={<OvertimePage />} />
        <Route path="/nhan-vien" element={<EmployeesPage />} />
        <Route path="/dang-ky-khuon-mat" element={<EnrollmentPage />} />
        <Route path="/don-nghi" element={<LeavePage />} />
        <Route path="/bao-cao" element={<ReportsPage />} />
        <Route path="/camera" element={<CameraPage />} />
        <Route path="/cai-dat" element={<SettingsPage />} />
        <Route path="/nhat-ky" element={<LogsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

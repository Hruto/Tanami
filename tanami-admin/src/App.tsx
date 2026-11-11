import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Shell } from "./components/Shell";
import { Empty } from "./components/States";
import { ToastProvider } from "./components/Toast";
import { canUse, type Area } from "./lib/access";
import { Announcements } from "./pages/Announcements";
import { Diseases } from "./pages/Diseases";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Reports } from "./pages/Reports";
import { Review } from "./pages/Review";
import { Users } from "./pages/Users";

function Guard({ area, children }: { area: Area; children: ReactNode }) {
  const { user } = useAuth();
  if (!canUse(user?.role, area)) {
    return (
      <Empty title="Halaman ini tidak tersedia untuk peran Anda">
        Minta admin mengubah peran akun Anda bila Anda memerlukan akses ini.
      </Empty>
    );
  }
  return <>{children}</>;
}

function Routed() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="splash">Memuat ruang kerja...</div>;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="laporan" element={<Guard area="reports"><Reports /></Guard>} />
        <Route path="tinjauan" element={<Guard area="review"><Review /></Guard>} />
        <Route path="penyakit" element={<Guard area="diseases"><Diseases /></Guard>} />
        <Route path="pengguna" element={<Guard area="users"><Users /></Guard>} />
        <Route path="pengumuman" element={<Guard area="announcements"><Announcements /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter
      basename={import.meta.env.BASE_URL}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ToastProvider>
        <AuthProvider>
          <Routed />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}

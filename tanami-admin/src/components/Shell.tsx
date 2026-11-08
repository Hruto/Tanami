import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { apiGet } from "../api/client";
import type { Overview } from "../api/types";
import { useAuth, useMe } from "../auth/AuthContext";
import { canUse, type Area } from "../lib/access";
import { ROLE_LABEL } from "../lib/labels";
import { IconBook, IconFlag, IconLens, IconMegaphone, IconMenu, IconPeople, IconSprout, LeafMark } from "./Icons";

interface NavItem {
  area: Area;
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export const NAV: NavItem[] = [
  { area: "overview", to: "/", label: "Ringkasan", icon: IconSprout },
  { area: "reports", to: "/laporan", label: "Laporan forum", icon: IconFlag },
  { area: "review", to: "/tinjauan", label: "Tinjauan deteksi", icon: IconLens },
  { area: "diseases", to: "/penyakit", label: "Basis penyakit", icon: IconBook },
  { area: "users", to: "/pengguna", label: "Pengguna", icon: IconPeople },
  { area: "announcements", to: "/pengumuman", label: "Pengumuman", icon: IconMegaphone },
];

function Wordmark() {
  return (
    <NavLink to="/" className="wordmark">
      <LeafMark />
      <span>
        <span className="wordmark-name">Tanami</span>
        <span className="wordmark-sub">Ruang kerja tim</span>
      </span>
    </NavLink>
  );
}

export function Shell() {
  const me = useMe();
  const { signOut } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [queues, setQueues] = useState<Overview["queues"] | null>(null);

  // Queue sizes beside the nav items: refreshed on navigation and after a
  // report or review is resolved.
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const bump = () => setRefresh((value) => value + 1);
    window.addEventListener("tanami:queues-changed", bump);
    return () => window.removeEventListener("tanami:queues-changed", bump);
  }, []);
  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);
  useEffect(() => {
    apiGet<Overview>("/admin/overview")
      .then((data) => setQueues(data.queues))
      .catch(() => setQueues(null));
  }, [location.pathname, refresh]);

  const counts: Partial<Record<Area, number>> = {
    reports: queues?.open_reports,
    review: queues?.feedback_pending,
  };

  return (
    <div className="shell" data-menu={menuOpen ? "open" : "closed"}>
      <header className="topbar">
        <button
          type="button"
          className="menu-button"
          aria-label="Buka menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <IconMenu />
        </button>
        <span className="wordmark-name">Tanami</span>
      </header>

      {menuOpen ? (
        <button type="button" className="scrim" aria-label="Tutup menu" onClick={() => setMenuOpen(false)} />
      ) : null}
      <aside className="rail" aria-label="Navigasi utama">
        <Wordmark />
        <nav className="nav">
          {NAV.filter((item) => canUse(me.role, item.area)).map((item) => {
            const Icon = item.icon;
            const count = counts[item.area];
            return (
              <NavLink key={item.to} to={item.to} end={item.to === "/"} className="nav-link">
                <Icon />
                <span>{item.label}</span>
                {count ? (
                  <span className="nav-count num" aria-label={`${count} menunggu`}>
                    {count}
                  </span>
                ) : null}
              </NavLink>
            );
          })}
        </nav>
        <div className="rail-foot">
          <div className="rail-user">{me.full_name}</div>
          <div className="rail-role">
            {ROLE_LABEL[me.role]}, @{me.username}
          </div>
          <button type="button" className="rail-signout" onClick={() => void signOut()}>
            Keluar
          </button>
        </div>
      </aside>

      <main className="workspace">
        <div className="workspace-inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

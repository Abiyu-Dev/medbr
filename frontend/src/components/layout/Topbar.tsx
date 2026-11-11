import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/auth/AuthContext";
import { useAlerts } from "@/hooks/useAlerts";
import { getNavigation } from "./navigation";
import { ROLE_LABELS } from "@/lib/permissions";
import { initials } from "@/lib/formatters";
import { TONE_HEX } from "@/lib/status";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/profile": "My Profile",
  "/facilities": "Facilities",
  "/applications": "Facility Applications",
  "/map": "Facility Map",
  "/inventory": "Inventory",
  "/products": "Product Catalogue",
  "/batches": "Stock Batches",
  "/movements": "Stock Movements",
  "/expiring": "Near-Expiry Stock",
  "/shortages": "Shortage Forecast",
  "/equipment": "Equipment",
  "/transfers": "Transfers",
  "/supply-gaps": "Supply Gaps",
  "/patients": "Vaccination Patients",
  "/vaccination-records": "Vaccination Records",
  "/followups": "Follow-ups",
  "/schedules": "Vaccine Schedules",
  "/ai": "AI Recommendations",
  "/audit": "Audit Log",
  "/facility": "Facility Profile",
  "/users": "Staff & Users",
};

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { items, count } = useAlerts();
  const [notifOpen, setNotifOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setNotifOpen(false);
        setUserOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => {
    setNotifOpen(false);
    setUserOpen(false);
  }, [location.pathname]);

  if (!user) return null;
  const navTitle = getNavigation(user)
    .flatMap((s) => s.items)
    .find((i) => i.to === location.pathname)?.label;
  const title = navTitle || TITLES[location.pathname] || "MedBridge";

  return (
    <header className="topbar" ref={ref}>
      <button className="icon-btn menu-toggle" onClick={onMenu} aria-label="Open menu">
        <Icon name="menu" size={19} />
      </button>
      <div className="topbar-title">{title}</div>
      <div className="topbar-spacer" />

      <div style={{ position: "relative" }}>
        <button
          className="icon-btn"
          onClick={() => {
            setNotifOpen((v) => !v);
            setUserOpen(false);
          }}
          aria-label="Notifications"
        >
          <Icon name="bell" size={18} />
          {count > 0 && <span className="dot" />}
        </button>
        {notifOpen && (
          <div className="dropdown" style={dropdownStyle}>
            <div className="dropdown-header">
              <strong>Alerts</strong>
              <span className="badge badge-teal">{count}</span>
            </div>
            {items.length === 0 ? (
              <div className="muted" style={{ padding: 20, textAlign: "center", fontSize: 13 }}>
                <Icon name="check-circle" size={22} style={{ color: "var(--lime)", marginBottom: 6 }} />
                <div>All clear. No operational alerts.</div>
              </div>
            ) : (
              items.map((a, i) => (
                <Link key={i} to={a.to} className="dropdown-item" onClick={() => setNotifOpen(false)}>
                  <span
                    className="dropdown-icon"
                    style={{ background: `${TONE_HEX[a.tone]}1a`, color: TONE_HEX[a.tone] }}
                  >
                    <Icon name={a.icon} size={16} />
                  </span>
                  <span style={{ flex: 1, fontSize: 13 }}>{a.label}</span>
                  <Icon name="chevron-right" size={15} className="faint" />
                </Link>
              ))
            )}
          </div>
        )}
      </div>

      <div style={{ position: "relative" }}>
        <button
          className="row"
          style={{ background: "none", border: "none", cursor: "pointer", gap: 9, padding: 4 }}
          onClick={() => {
            setUserOpen((v) => !v);
            setNotifOpen(false);
          }}
        >
          <div className="avatar avatar-sm">{initials(user.username)}</div>
          <span className="hide-mobile" style={{ fontSize: 13, fontWeight: 600 }}>
            {user.username}
          </span>
          <Icon name="chevron-down" size={15} className="faint hide-mobile" />
        </button>
        {userOpen && (
          <div className="dropdown" style={{ ...dropdownStyle, width: 240 }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{user.username}</div>
              <div className="muted" style={{ fontSize: 12 }}>{ROLE_LABELS[user.role]}</div>
              {user.facility_name && (
                <div className="faint" style={{ fontSize: 12, marginTop: 2 }}>{user.facility_name}</div>
              )}
            </div>
            <button className="dropdown-item" onClick={() => navigate("/profile")}>
              <Icon name="user" size={16} /> My Profile
            </button>
            <button
              className="dropdown-item"
              style={{ color: "var(--red)" }}
              onClick={logout}
            >
              <Icon name="logout" size={16} /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

const dropdownStyle: React.CSSProperties = {
  position: "absolute",
  top: "calc(100% + 10px)",
  right: 0,
  width: 340,
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-md)",
  boxShadow: "var(--sh-lg)",
  zIndex: 60,
  overflow: "hidden",
  animation: "modal-in .18s ease",
};
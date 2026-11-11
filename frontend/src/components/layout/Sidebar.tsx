import { NavLink } from "react-router-dom";
import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/auth/AuthContext";
import { getNavigation } from "./navigation";
import { ROLE_LABELS } from "@/lib/permissions";
import { initials } from "@/lib/formatters";

export function Sidebar({
  open,
  onClose,
  providesVaccination,
}: {
  open: boolean;
  onClose: () => void;
  providesVaccination: boolean;
}) {
  const { user, logout } = useAuth();
  if (!user) return null;
  const sections = getNavigation(user).filter((s) => !s.vaccination || providesVaccination);

  return (
    <>
      {open && <div className="sidebar-scrim" onClick={onClose} />}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-mark">
            <Icon name="heart" size={22} />
          </div>
          <div className="brand-text">
            <strong>MedBridge</strong>
            <span>Ethiopia</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {sections.map((section) => (
            <div className="nav-section" key={section.label}>
              <div className="nav-section-label">{section.label}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                  onClick={onClose}
                >
                  <Icon name={item.icon} size={18} className="nav-icon" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="avatar">{initials(user.username)}</div>
            <div className="sidebar-user-meta">
              <strong>{user.username}</strong>
              <span>{ROLE_LABELS[user.role]}</span>
            </div>
            <button
              className="close-btn"
              style={{ background: "rgba(255,255,255,.06)", color: "#9fc3be" }}
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
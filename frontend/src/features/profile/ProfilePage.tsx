import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { ROLE_LABELS, isCentral } from "@/lib/permissions";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Icon,
  PageHeader,
} from "@/components/ui";
import { formatDate, initials } from "@/lib/formatters";

export function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;

  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <PageHeader eyebrow="Account" title="Your profile" description="Identity, role and facility assignment for this session." />

      <Card>
        <CardBody>
          <div className="row" style={{ gap: 18, alignItems: "center" }}>
            <div className="avatar avatar-lg">{initials(fullName)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontSize: 22 }}>{fullName}</h2>
              <div className="row wrap" style={{ gap: 8, marginTop: 6 }}>
                <Badge tone="teal" dot={false}>{ROLE_LABELS[user.role]}</Badge>
                <span className="mono muted">@{user.username}</span>
                {user.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="slate">Inactive</Badge>}
              </div>
            </div>
          </div>

          <div className="divider" />

          <div className="detail-grid">
            <div className="detail-item"><div className="dt">Email</div><div className="dd">{user.email || "—"}</div></div>
            <div className="detail-item"><div className="dt">Phone</div><div className="dd">{user.phone || "—"}</div></div>
            <div className="detail-item"><div className="dt">Role</div><div className="dd">{ROLE_LABELS[user.role]}</div></div>
            <div className="detail-item"><div className="dt">Joined</div><div className="dd">{formatDate(user.date_joined)}</div></div>
            <div className="detail-item">
              <div className="dt">Facility</div>
              <div className="dd">
                {user.facility ? (
                  <button className="btn btn-ghost btn-sm" style={{ padding: 0 }} onClick={() => navigate("/facility")}>
                    {user.facility_name || `Facility #${user.facility}`} <Icon name="arrow-up-right" size={13} />
                  </button>
                ) : (
                  isCentral(user.role) ? "Central / network-wide" : "Not assigned"
                )}
              </div>
            </div>
            {user.facility_status && (
              <div className="detail-item"><div className="dt">Facility status</div><div className="dd"><Badge value={user.facility_status} /></div></div>
            )}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Session & access" subtitle="Permissions are enforced by the server, not this screen." icon="shield" />
        <CardBody>
          <div className="alert alert-info">
            <Icon name="info" size={17} />
            <span>
              Your access token refreshes automatically and expires after 60 minutes of inactivity.
              If a refresh fails you'll be returned to the sign-in screen. Signing out clears all
              cached facility and patient data from this browser.
            </span>
          </div>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button variant="danger" icon="logout" onClick={logout}>Sign out</Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
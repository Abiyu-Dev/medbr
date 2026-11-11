import { useNavigate } from "react-router-dom";
import { Button, Icon } from "@/components/ui";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="empty-state" style={{ paddingTop: 80 }}>
      <div className="empty-icon" style={{ background: "var(--surface-3)", color: "var(--muted)" }}>
        <Icon name="search" size={28} />
      </div>
      <h3 style={{ fontSize: 20 }}>Page not found</h3>
      <p>This page doesn't exist, or it isn't available for your role and facility.</p>
      <div style={{ marginTop: 18 }}>
        <Button icon="dashboard" onClick={() => navigate("/")}>Back to dashboard</Button>
      </div>
    </div>
  );
}
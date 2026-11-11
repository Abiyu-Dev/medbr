import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { Button } from "./Button";
import { errorMessage } from "@/api/client";

export function Spinner({ large }: { large?: boolean }) {
  return <div className={`spinner ${large ? "spinner-lg" : ""}`} />;
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-state">
      <Spinner large />
      <span>{label}</span>
    </div>
  );
}

export function FullLoader() {
  return (
    <div className="full-loader">
      <div style={{ textAlign: "center" }}>
        <div className="brand-mark" style={{ margin: "0 auto 18px", width: 52, height: 52 }}>
          <Icon name="heart" size={26} />
        </div>
        <Spinner large />
      </div>
    </div>
  );
}

export function EmptyState({
  icon = "inbox",
  title,
  message,
  action,
}: {
  icon?: IconName;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} size={28} />
      </div>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action && <div style={{ marginTop: 18 }}>{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Could not load data",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div className="error-state">
      <div className="error-icon">
        <Icon name="alert" size={26} />
      </div>
      <h3 style={{ fontSize: 16, marginBottom: 6 }}>{title}</h3>
      <p className="muted" style={{ maxWidth: "44ch", margin: "0 auto 16px" }}>
        {errorMessage(error)}
      </p>
      {onRetry && (
        <Button variant="secondary" icon="refresh" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div style={{ padding: 16 }}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} style={{ display: "flex", gap: 16, marginBottom: 14 }}>
          {Array.from({ length: cols }).map((_, c) => (
            <div
              key={c}
              className="skeleton"
              style={{ height: 16, flex: c === 0 ? 2 : 1 }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
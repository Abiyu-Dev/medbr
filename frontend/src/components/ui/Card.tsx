import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import type { Tone } from "@/lib/status";
import { TONE_HEX } from "@/lib/status";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function CardHeader({
  title,
  subtitle,
  action,
  icon,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="card-header">
      <div className="row" style={{ gap: 10 }}>
        {icon && (
          <span style={{ color: "var(--brand)", display: "grid", placeItems: "center" }}>
            <Icon name={icon} size={18} />
          </span>
        )}
        <div>
          <h3>{title}</h3>
          {subtitle && <div className="subtitle">{subtitle}</div>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function CardBody({
  children,
  tight,
}: {
  children: ReactNode;
  tight?: boolean;
}) {
  return <div className={`card-body ${tight ? "tight" : ""}`}>{children}</div>;
}

const TONE_SOFT: Record<Tone, string> = {
  green: "var(--lime-050)",
  amber: "var(--amber-050)",
  red: "var(--red-050)",
  blue: "var(--blue-050)",
  violet: "var(--violet-050)",
  slate: "var(--surface-3)",
  teal: "var(--brand-050)",
};

export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "teal",
  onClick,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon: IconName;
  tone?: Tone;
  onClick?: () => void;
}) {
  return (
    <div
      className={`stat-card ${onClick ? "clickable" : ""}`}
      style={
        {
          "--accent": TONE_HEX[tone],
          "--accent-soft": TONE_SOFT[tone],
        } as React.CSSProperties
      }
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className="stat-top">
        <div className="stat-icon">
          <Icon name={icon} size={21} />
        </div>
      </div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}
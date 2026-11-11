import type { ReactNode } from "react";
import { toneFor, type Tone } from "@/lib/status";
import { humanize } from "@/lib/formatters";

interface BadgeProps {
  tone?: Tone;
  value?: string | null;
  children?: ReactNode;
  dot?: boolean;
}

export function Badge({ tone, value, children, dot = true }: BadgeProps) {
  const t = tone ?? toneFor(value);
  const label = children ?? (value ? humanize(value) : "—");
  return (
    <span className={`badge badge-${t}`}>
      {dot && <span className="dot" />}
      {label}
    </span>
  );
}
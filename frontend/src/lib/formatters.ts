const TZ = "Africa/Addis_Ababa";

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  // Date-only strings (YYYY-MM-DD) are parsed as local; keep them calendar-stable.
  const d = value.length === 10 ? new Date(value + "T00:00:00") : new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: value.length === 10 ? undefined : TZ,
  });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  });
}

export function formatTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  });
}

export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  const diff = Date.now() - d.getTime();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ${diff >= 0 ? "ago" : "from now"}`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ${diff >= 0 ? "ago" : "from now"}`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ${diff >= 0 ? "ago" : "from now"}`;
  return formatDate(value);
}

export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US");
}

export function formatDecimal(value?: string | number | null, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatMoney(value?: string | number | null, currency = "ETB"): string {
  if (value === null || value === undefined || value === "") return "—";
  return `${formatDecimal(value)} ${currency}`;
}

export function daysUntil(dateStr?: string | null): number | null {
  if (!dateStr) return null;
  const d = new Date(dateStr.length === 10 ? dateStr + "T00:00:00" : dateStr);
  if (isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86400000);
}

const ACRONYMS: Record<string, string> = { ai: "AI", id: "ID" };

export function humanize(value?: string | null): string {
  if (!value) return "—";
  return value
    .toLowerCase()
    .split("_")
    .map((w) => ACRONYMS[w] ?? w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
}

export function ageFromDob(dob?: string | null): string {
  if (!dob) return "—";
  const days = daysUntil(dob);
  if (days === null) return "—";
  const ageDays = -days;
  if (ageDays < 0) return "—";
  if (ageDays < 60) return `${ageDays}d`;
  const months = Math.floor(ageDays / 30.44);
  if (months < 24) return `${months}mo`;
  return `${Math.floor(months / 12)}y`;
}

// Convert a local datetime-local input value to an ISO UTC string with Z.
export function localInputToISO(value?: string | null): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

export function nowLocalInput(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000);
  return local.toISOString().slice(0, 16);
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
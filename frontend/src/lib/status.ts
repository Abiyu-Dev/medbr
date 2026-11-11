export type Tone = "green" | "amber" | "red" | "blue" | "violet" | "slate" | "teal";

const TONE_MAP: Record<string, Tone> = {
  // Facility
  PENDING: "amber",
  APPROVED: "green",
  REJECTED: "red",
  SUSPENDED: "slate",
  // Storage
  OK: "green",
  QUARANTINED: "amber",
  TEMPERATURE_EXCURSION: "red",
  DAMAGED: "red",
  EXPIRED: "slate",
  // Transfer
  DRAFT: "slate",
  REQUESTED: "blue",
  UNDER_REVIEW: "amber",
  DISPATCHED: "violet",
  IN_TRANSIT: "blue",
  RECEIVED: "green",
  CANCELLED: "slate",
  FAILED: "red",
  // Priority
  CRITICAL: "red",
  HIGH: "amber",
  MEDIUM: "blue",
  LOW: "slate",
  // Gap
  OPEN: "red",
  ASSIGNED: "blue",
  ACTION_PLANNED: "violet",
  ESCALATED: "red",
  RESOLVED: "green",
  CLOSED: "slate",
  // Follow-up
  UPCOMING: "blue",
  DUE: "amber",
  OVERDUE: "red",
  COMPLETED: "green",
  CONTACT_ATTEMPTED: "violet",
  REVIEW_REQUIRED: "amber",
  // AI
  PENDING_REVIEW: "amber",
  INVALID: "red",
  // Equipment
  OPERATIONAL: "green",
  NEEDS_MAINTENANCE: "amber",
  OUT_OF_SERVICE: "red",
  // Delivery
  NOT_ARRANGED: "slate",
  ARRANGED_BY_PHONE: "blue",
  DISCREPANCY: "amber",
  // Category
  MEDICINE: "blue",
  VACCINE: "teal",
  // Movement direction
  IN: "green",
  OUT: "amber",
};

export function toneFor(value?: string | null): Tone {
  if (!value) return "slate";
  return TONE_MAP[value] ?? "slate";
}

export const TONE_HEX: Record<Tone, string> = {
  green: "#4f9d2a",
  amber: "#e08a00",
  red: "#dd403a",
  blue: "#2f6fed",
  violet: "#8b46c9",
  slate: "#8b9795",
  teal: "#0d7d74",
};

// Chart palette — six separable hues.
export const CHART_COLORS = ["#0d7d74", "#2f6fed", "#e08a00", "#8b46c9", "#dd403a", "#4f9d2a"];
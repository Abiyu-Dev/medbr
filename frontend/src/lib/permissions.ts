import type { Role, TransferRequest, UserProfile } from "@/api/types";

export const CENTRAL_ROLES: Role[] = ["SYSTEM_ADMIN", "CENTRAL_COORDINATOR"];
export const STOCK_ROLES: Role[] = [
  "SYSTEM_ADMIN",
  "FACILITY_MANAGER",
  "PHARMACIST",
  "INVENTORY_STAFF",
  "PHARMACY_STAFF",
];
export const VACCINATION_ROLES: Role[] = ["HEALTH_WORKER", "FACILITY_MANAGER", "SYSTEM_ADMIN"];

export const isCentral = (role?: Role | null) => !!role && CENTRAL_ROLES.includes(role);
export const isAdmin = (role?: Role | null) => role === "SYSTEM_ADMIN";
export const isManager = (role?: Role | null) => role === "FACILITY_MANAGER";

export const canManageStock = (role?: Role | null) => !!role && STOCK_ROLES.includes(role);
export const canAdjustStock = (role?: Role | null) =>
  role === "SYSTEM_ADMIN" || role === "FACILITY_MANAGER";
export const canRequestTransfer = (role?: Role | null) =>
  !!role &&
  ["SYSTEM_ADMIN", "CENTRAL_COORDINATOR", "FACILITY_MANAGER", "PHARMACIST", "INVENTORY_STAFF"].includes(
    role,
  );
export const canManageUsers = (role?: Role | null) =>
  role === "SYSTEM_ADMIN" || role === "FACILITY_MANAGER";
export const canCreateProduct = (role?: Role | null) => role === "SYSTEM_ADMIN";
export const canManageSchedules = (role?: Role | null) =>
  role === "SYSTEM_ADMIN" || role === "CENTRAL_COORDINATOR";
export const canVaccinate = (role?: Role | null) => !!role && VACCINATION_ROLES.includes(role);
export const canRunInventoryAI = (role?: Role | null) =>
  !!role && ["SYSTEM_ADMIN", "CENTRAL_COORDINATOR", "FACILITY_MANAGER", "PHARMACIST"].includes(role);
export const canRunVaccinationAI = (role?: Role | null) =>
  role === "SYSTEM_ADMIN" || role === "CENTRAL_COORDINATOR" || role === "HEALTH_WORKER";
export const canReviewAI = (role?: Role | null) =>
  role === "SYSTEM_ADMIN" || role === "CENTRAL_COORDINATOR" || role === "FACILITY_MANAGER";

export function canApproveTransfer(user: UserProfile | null, t: TransferRequest): boolean {
  if (!user) return false;
  if (!["REQUESTED", "UNDER_REVIEW"].includes(t.status)) return false;
  if (isCentral(user.role)) return true;
  return isManager(user.role) && user.facility === t.source_facility;
}

export function canRejectTransfer(user: UserProfile | null, t: TransferRequest): boolean {
  if (!user) return false;
  if (!["REQUESTED", "UNDER_REVIEW"].includes(t.status)) return false;
  if (isCentral(user.role)) return true;
  return (
    isManager(user.role) &&
    (user.facility === t.source_facility || user.facility === t.destination_facility)
  );
}

export function canDispatch(user: UserProfile | null, t: TransferRequest): boolean {
  if (!user || t.status !== "APPROVED") return false;
  if (isCentral(user.role)) return true;
  return (
    ["FACILITY_MANAGER", "PHARMACIST", "INVENTORY_STAFF"].includes(user.role) &&
    user.facility === t.source_facility
  );
}

export function canConfirmReceipt(user: UserProfile | null, t: TransferRequest): boolean {
  if (!user || !["DISPATCHED", "IN_TRANSIT"].includes(t.status)) return false;
  if (isCentral(user.role)) return true;
  return (
    ["FACILITY_MANAGER", "PHARMACIST", "INVENTORY_STAFF"].includes(user.role) &&
    user.facility === t.destination_facility
  );
}

export function canCancelTransfer(user: UserProfile | null, t: TransferRequest): boolean {
  if (!user || !["REQUESTED", "UNDER_REVIEW", "APPROVED"].includes(t.status)) return false;
  if (isCentral(user.role)) return true;
  return user.facility === t.source_facility || user.facility === t.destination_facility;
}

export const ROLE_LABELS: Record<Role, string> = {
  SYSTEM_ADMIN: "System Admin",
  CENTRAL_COORDINATOR: "Central Coordinator",
  FACILITY_MANAGER: "Facility Manager",
  PHARMACIST: "Pharmacist",
  INVENTORY_STAFF: "Inventory Staff",
  PHARMACY_STAFF: "Pharmacy Staff",
  HEALTH_WORKER: "Health Worker",
};
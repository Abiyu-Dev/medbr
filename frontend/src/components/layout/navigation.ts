import type { UserProfile } from "@/api/types";
import type { IconName } from "@/components/ui/Icon";
import { canManageStock, canVaccinate, isCentral, isManager } from "@/lib/permissions";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  vaccination?: boolean;
}
export interface NavSection {
  label: string;
  items: NavItem[];
  vaccination?: boolean;
}

export function getNavigation(user: UserProfile): NavSection[] {
  const role = user.role;
  const sections: NavSection[] = [
    { label: "Overview", items: [{ to: "/", label: "Dashboard", icon: "dashboard", end: true }] },
  ];

  if (isCentral(role)) {
    sections.push({
      label: "Coordination",
      items: [
        { to: "/supply-gaps", label: "Supply Gaps", icon: "gap" },
        { to: "/supply-requests", label: "Supply Requests", icon: "truck" },
        { to: "/transfers", label: "Transfers", icon: "transfer" },
        { to: "/ai", label: "AI Recommendations", icon: "sparkles" },
        { to: "/map", label: "Facility Map", icon: "map" },
      ],
    });
    sections.push({
      label: "Network",
      items: [
        { to: "/facilities", label: "Facilities", icon: "building" },
        { to: "/applications", label: "Applications", icon: "clipboard" },
        { to: "/inventory", label: "Nationwide Stock", icon: "box" },
        { to: "/products", label: "Product Catalogue", icon: "pill" },
      ],
    });
    sections.push({
      label: "Vaccination",
      items: [{ to: "/schedules", label: "Vaccine Schedules", icon: "calendar" }],
    });
    sections.push({
      label: "Administration",
      items: [{ to: "/audit", label: "Audit Log", icon: "audit" }],
    });
    return sections;
  }

  if (canManageStock(role)) {
    sections.push({
      label: "Inventory",
      items: [
        { to: "/inventory", label: "Stock Summary", icon: "box" },
        { to: "/batches", label: "Batches", icon: "layers" },
        { to: "/movements", label: "Stock Movements", icon: "activity" },
        { to: "/expiring", label: "Near Expiry", icon: "clock" },
        { to: "/shortages", label: "Shortages", icon: "alert" },
        { to: "/equipment", label: "Equipment", icon: "flask" },
        { to: "/products", label: "Product Catalogue", icon: "pill" },
      ],
    });
    sections.push({
      label: "Transfers",
      items: [
        { to: "/transfers", label: "Transfers", icon: "transfer" },
        { to: "/supply-requests", label: "Supply Requests", icon: "truck" },
      ],
    });
  }

  if (canVaccinate(role)) {
    sections.push({
      label: "Vaccination",
      vaccination: true,
      items: [
        { to: "/patients", label: "Patients", icon: "user" },
        { to: "/vaccination-records", label: "Dose Records", icon: "syringe" },
        { to: "/followups", label: "Follow-ups", icon: "calendar" },
        { to: "/schedules", label: "Schedule Reference", icon: "clipboard" },
      ],
    });
  }

  const facilityItems: NavItem[] = [
    { to: "/facility", label: "Facility Profile", icon: "building" },
  ];
  if (isManager(role)) facilityItems.push({ to: "/users", label: "Staff & Users", icon: "users" });
  facilityItems.push({ to: "/ai", label: "AI Insights", icon: "sparkles" });
  facilityItems.push({ to: "/audit", label: "Activity Log", icon: "audit" });
  sections.push({ label: "Facility", items: facilityItems });

  return sections;
}
import { useQuery } from "@tanstack/react-query";
import { DashboardApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import type { IconName } from "@/components/ui/Icon";
import type { Tone } from "@/lib/status";

export interface AlertItem {
  icon: IconName;
  tone: Tone;
  label: string;
  to: string;
}

export function useAlerts() {
  const { user } = useAuth();
  const central = isCentral(user?.role);
  const facilityId = user?.facility ?? null;

  const facilityQuery = useQuery({
    queryKey: ["dashboard", "facility", facilityId],
    queryFn: () => DashboardApi.facility(),
    enabled: !central && !!facilityId,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const centralQuery = useQuery({
    queryKey: ["dashboard", "central"],
    queryFn: () => DashboardApi.central(),
    enabled: central,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const items: AlertItem[] = [];
  if (central && centralQuery.data) {
    const d = centralQuery.data;
    if (d.facilities.pending_applications > 0)
      items.push({ icon: "clipboard", tone: "amber", label: `${d.facilities.pending_applications} facility application(s) awaiting review`, to: "/applications" });
    if (d.supply_gaps.critical_active > 0)
      items.push({ icon: "gap", tone: "red", label: `${d.supply_gaps.critical_active} critical supply gap(s)`, to: "/supply-gaps" });
    if (d.transfers.requested > 0)
      items.push({ icon: "transfer", tone: "blue", label: `${d.transfers.requested} transfer(s) awaiting review`, to: "/transfers" });
    if (d.transfers.dispatched > 0)
      items.push({ icon: "truck", tone: "violet", label: `${d.transfers.dispatched} shipment(s) in transit`, to: "/transfers" });
    if (d.ai_recommendations.pending_review > 0)
      items.push({ icon: "sparkles", tone: "violet", label: `${d.ai_recommendations.pending_review} AI recommendation(s) to review`, to: "/ai" });
    if (d.vaccinations.overdue > 0)
      items.push({ icon: "syringe", tone: "red", label: `${d.vaccinations.overdue} overdue vaccination follow-up(s) network-wide`, to: "/ai" });
  } else if (facilityQuery.data) {
    const d = facilityQuery.data;
    if (d.inventory.critical_shortages > 0)
      items.push({ icon: "alert", tone: "red", label: `${d.inventory.critical_shortages} critical shortage(s)`, to: "/shortages" });
    if (d.inventory.products_with_gap > 0)
      items.push({ icon: "gap", tone: "amber", label: `${d.inventory.products_with_gap} product(s) with projected gap`, to: "/shortages" });
    if (d.near_expiry.length > 0)
      items.push({ icon: "clock", tone: "amber", label: `${d.near_expiry.length} batch(es) nearing expiry`, to: "/expiring" });
    if (d.vaccinations.overdue > 0)
      items.push({ icon: "syringe", tone: "red", label: `${d.vaccinations.overdue} overdue follow-up(s)`, to: "/followups" });
    const incoming = d.transfers.incoming.filter((t) => ["DISPATCHED", "IN_TRANSIT"].includes(t.status));
    if (incoming.length > 0)
      items.push({ icon: "truck", tone: "blue", label: `${incoming.length} incoming shipment(s) to receive`, to: "/transfers" });
  }

  return { items, count: items.length };
}
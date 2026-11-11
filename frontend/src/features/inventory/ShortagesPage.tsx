import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { InventoryApi } from "@/api/endpoints";
import { canRunInventoryAI } from "@/lib/permissions";
import { useAuth } from "@/auth/AuthContext";
import { BarChart } from "@/components/charts/Charts";
import { Button, Card, CardBody, CardHeader, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/formatters";
import { CHART_COLORS } from "@/lib/status";
import { AnalyzeModal } from "@/features/ai/AnalyzeModal";
import { useInventoryScope, FacilityScopeBar } from "./InventoryScope";
import { InventoryItemsTable } from "./InventoryItemsTable";

export function ShortagesPage() {
  const { user } = useAuth();
  const scope = useInventoryScope();
  const [showAnalyze, setShowAnalyze] = useState(false);
  const q = useQuery({
    queryKey: ["inventory", "shortages", scope.params],
    queryFn: () => InventoryApi.shortages(scope.params),
    enabled: scope.enabled,
    staleTime: 60_000,
  });
  const items = (q.data?.items ?? []).filter((i) => (i.projected_gap ?? 0) > 0);
  const totalGap = items.reduce((s, i) => s + (i.projected_gap ?? 0), 0);
  const chart = [...items]
    .sort((a, b) => (b.projected_gap ?? 0) - (a.projected_gap ?? 0))
    .slice(0, 8)
    .map((i, idx) => ({ label: i.product_name, value: i.projected_gap ?? 0, color: CHART_COLORS[idx % CHART_COLORS.length] }));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Inventory"
        title="Projected shortages"
        description="Products whose usable stock plus reliable incoming transfers will not cover projected demand."
        actions={canRunInventoryAI(user?.role) && <Button icon="sparkles" onClick={() => setShowAnalyze(true)}>Request transfer with AI</Button>}
      />
      {scope.central && <FacilityScopeBar facilityId={scope.facilityId} onChange={scope.setFacilityId} />}
      {!scope.enabled ? (
        <Card><EmptyState icon="building" title="Select a facility" message="Choose a facility to see its projected shortages." /></Card>
      ) : q.isLoading ? (
        <LoadingState label="Calculating projections…" />
      ) : q.error || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="stat-grid stagger">
            <StatCard label="Products short" value={formatNumber(items.length)} sub="with uncovered demand" icon="gap" tone={items.length ? "red" : "green"} />
            <StatCard label="Uncovered units" value={formatNumber(totalGap)} sub={`over ${q.data.horizon_days} days`} icon="alert" tone={totalGap ? "amber" : "green"} />
          </div>
          {items.length === 0 ? (
            <Card><EmptyState icon="check-circle" title="No projected shortages" message="Every product with known demand is covered by stock and incoming transfers." /></Card>
          ) : (
            <>
              <Card>
                <CardHeader title="Largest gaps" subtitle="Uncovered units by product" icon="gap" />
                <CardBody><BarChart data={chart} formatValue={(v) => formatNumber(v)} /></CardBody>
              </Card>
              <Card>
                <CardHeader title={q.data.facility_name} subtitle={`As of ${formatDate(q.data.as_of)} · ${q.data.horizon_days}-day horizon`} icon="alert" />
                <InventoryItemsTable items={items} emptyTitle="No shortages" />
              </Card>
            </>
          )}
        </>
      )}
      {showAnalyze && (
        <AnalyzeModal
          initialType="INVENTORY_ANALYSIS"
          initialFacilityId={scope.facilityId}
          onClose={() => setShowAnalyze(false)}
        />
      )}
    </div>
  );
}
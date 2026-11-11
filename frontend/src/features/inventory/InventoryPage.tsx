import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { InventoryApi } from "@/api/endpoints";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/formatters";
import { useInventoryScope, FacilityScopeBar } from "./InventoryScope";
import { InventoryItemsTable } from "./InventoryItemsTable";

export function InventoryPage() {
  const navigate = useNavigate();
  const scope = useInventoryScope();
  const q = useQuery({
    queryKey: ["inventory", "summary", scope.params],
    queryFn: () => InventoryApi.summary(scope.params),
    enabled: scope.enabled,
    staleTime: 60_000,
  });

  const items = q.data?.items ?? [];
  const usable = items.reduce((s, i) => s + i.usable_stock, 0);
  const gaps = items.filter((i) => (i.projected_gap ?? 0) > 0).length;
  const nearExpiry = items.reduce((s, i) => s + i.near_expiry_quantity, 0);
  const batches = items.reduce((s, i) => s + i.batch_count, 0);

  return (
    <div className="stack">
      <PageHeader
        eyebrow={scope.central ? "Nationwide stock" : "Inventory"}
        title="Stock summary"
        description="Usable, reserved and incoming stock per product with projected demand and days-of-stock."
        actions={<Button variant="secondary" icon="refresh" onClick={() => q.refetch()} disabled={!scope.enabled}>Refresh</Button>}
      />

      {scope.central && <FacilityScopeBar facilityId={scope.facilityId} onChange={scope.setFacilityId} />}

      {!scope.enabled ? (
        <Card><EmptyState icon="building" title="Select a facility" message="Choose a facility above to load its stock summary." /></Card>
      ) : q.isLoading ? (
        <LoadingState label="Loading stock summary…" />
      ) : q.error || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="stat-grid stagger">
            <StatCard label="Usable units" value={formatNumber(usable)} sub="across all products" icon="box" tone="teal" />
            <StatCard label="Products with gap" value={formatNumber(gaps)} sub="projected uncovered demand" icon="gap" tone={gaps ? "amber" : "green"} onClick={() => navigate("/shortages")} />
            <StatCard label="Near-expiry units" value={formatNumber(nearExpiry)} sub={`within ${q.data.near_expiry_days} days`} icon="clock" tone={nearExpiry ? "amber" : "slate"} onClick={() => navigate("/expiring")} />
            <StatCard label="Active batches" value={formatNumber(batches)} sub="lot-level records" icon="layers" tone="blue" onClick={() => navigate("/batches")} />
          </div>
          <Card>
            <CardHeader
              title={q.data.facility_name}
              subtitle={`As of ${formatDate(q.data.as_of)} · ${q.data.horizon_days}-day horizon · ${q.data.usage_window_days}-day usage window`}
              icon="box"
            />
            <InventoryItemsTable items={items} />
          </Card>
        </>
      )}
    </div>
  );
}
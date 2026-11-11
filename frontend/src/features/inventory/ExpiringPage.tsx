import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { InventoryApi } from "@/api/endpoints";
import type { ExpiringBatch } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { canManageStock, canRequestTransfer } from "@/lib/permissions";
import { Badge, Button, Card, CardHeader, DataTable, EmptyState, ErrorState, Icon, LoadingState, PageHeader, StatCard, type Column } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/formatters";
import { useInventoryScope, FacilityScopeBar } from "./InventoryScope";

export function ExpiringPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const scope = useInventoryScope();
  const q = useQuery({
    queryKey: ["expiring", scope.params],
    queryFn: () => InventoryApi.expiring(scope.params),
    enabled: scope.enabled,
    staleTime: 60_000,
  });
  const batches = q.data?.batches ?? [];
  const totalUnits = batches.reduce((s, b) => s + b.quantity_available, 0);
  const urgent = batches.filter((b) => b.days_until_expiry <= 30).length;

  const columns: Column<ExpiringBatch>[] = [
    {
      key: "product",
      header: "Product",
      render: (b) => (
        <div className="stack" style={{ gap: 3 }}>
          <span className="cell-title">{b.product_name}</span>
          <span className="cell-sub mono">{b.batch_number}</span>
        </div>
      ),
    },
    { key: "category", header: "Type", render: (b) => <Badge value={b.category} dot={false} /> },
    { key: "qty", header: "Available", align: "right", render: (b) => <strong>{formatNumber(b.quantity_available)}</strong> },
    { key: "expiry", header: "Expiry", render: (b) => formatDate(b.expiry_date) },
    {
      key: "days",
      header: "Time left",
      render: (b) => <Badge tone={b.days_until_expiry <= 30 ? "red" : "amber"} dot={false}>{b.days_until_expiry}d</Badge>,
    },
    { key: "storage", header: "Storage", render: (b) => <Badge value={b.storage_status} /> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Inventory"
        title="Near-expiry stock"
        description="Usable batches approaching expiry. Prioritize for use, or redistribute to a facility that needs them."
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            {canRequestTransfer(user?.role) && <Button variant="secondary" icon="transfer" onClick={() => navigate("/transfers?new=1")}>Redistribute</Button>}
            {canManageStock(user?.role) && <Button variant="secondary" icon="trash" onClick={() => navigate("/batches?action=wastage")}>Record wastage</Button>}
          </div>
        }
      />
      {scope.central && <FacilityScopeBar facilityId={scope.facilityId} onChange={scope.setFacilityId} />}
      {!scope.enabled ? (
        <Card><EmptyState icon="building" title="Select a facility" message="Choose a facility to see its near-expiry batches." /></Card>
      ) : q.isLoading ? (
        <LoadingState label="Loading near-expiry stock…" />
      ) : q.error || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="stat-grid stagger">
            <StatCard label="Expiring batches" value={formatNumber(batches.length)} sub={`within ${q.data.near_expiry_days} days`} icon="clock" tone={batches.length ? "amber" : "green"} />
            <StatCard label="Units at risk" value={formatNumber(totalUnits)} sub="usable units near expiry" icon="box" tone={totalUnits ? "amber" : "slate"} />
            <StatCard label="Expiring ≤ 30 days" value={formatNumber(urgent)} sub="need urgent action" icon="alert" tone={urgent ? "red" : "green"} />
          </div>
          {batches.length > 0 && (
            <div className="alert alert-warning">
              <Icon name="clock" size={17} />
              <span>Use these batches first (FEFO). If they cannot be consumed in time, request a transfer to a facility with demand, or record wastage once expired.</span>
            </div>
          )}
          <Card>
            <CardHeader title={q.data.facility_name} subtitle={`As of ${formatDate(q.data.as_of)}`} icon="clock" />
            <DataTable
              columns={columns}
              rows={batches}
              rowKey={(b) => b.batch_id}
              empty={{ icon: "check-circle", title: "No near-expiry stock", message: "No usable batches expire within the warning window." }}
            />
          </Card>
        </>
      )}
    </div>
  );
}
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { DashboardApi, InventoryApi } from "@/api/endpoints";
import type { StockMovement, TransferRequest } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import {
  canManageStock,
  canRequestTransfer,
  canVaccinate,
} from "@/lib/permissions";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Icon,
  LoadingState,
  PageHeader,
  StatCard,
} from "@/components/ui";
import { BarChart, DonutChart } from "@/components/charts/Charts";
import { CHART_COLORS } from "@/lib/status";
import {
  formatDate,
  formatNumber,
  humanize,
  relativeTime,
} from "@/lib/formatters";

function TransferRow({ t, onClick }: { t: TransferRequest; onClick: () => void }) {
  return (
    <button className="dropdown-item" onClick={onClick} style={{ gap: 12 }}>
      <span
        className="dropdown-icon"
        style={{ background: "var(--brand-050)", color: "var(--brand)" }}
      >
        <Icon name="transfer" size={16} />
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span className="cell-title truncate" style={{ display: "block" }}>
          {t.product_name} · {formatNumber(t.quantity_requested)}
        </span>
        <span className="cell-sub truncate" style={{ display: "block" }}>
          {t.source_facility_name} → {t.destination_facility_name}
        </span>
      </span>
      <Badge value={t.status} dot={false} />
    </button>
  );
}

function MovementRow({ m }: { m: StockMovement }) {
  const inbound = m.direction === "IN";
  return (
    <div className="timeline-item">
      <span
        className="timeline-dot"
        style={{
          background: inbound ? "var(--lime-050)" : "var(--amber-050)",
          color: inbound ? "var(--lime)" : "var(--amber)",
        }}
      >
        <Icon name={inbound ? "trend-down" : "trend-up"} size={15} />
      </span>
      <div className="timeline-content">
        <div className="t-title">
          {humanize(m.movement_type)} · {inbound ? "+" : "−"}
          {formatNumber(m.quantity)} {m.product_name}
        </div>
        <div className="t-meta">
          {m.batch_number} · {m.performed_by_username || "system"} · {relativeTime(m.occurred_at)}
        </div>
      </div>
    </div>
  );
}

export function FacilityDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const facilityId = user?.facility ?? null;

  const dash = useQuery({
    queryKey: ["dashboard", "facility", facilityId],
    queryFn: () => DashboardApi.facility(),
    enabled: !!facilityId,
    refetchInterval: 60_000,
  });

  const inv = useQuery({
    queryKey: ["dashboard", "facility-inventory", facilityId],
    queryFn: () => InventoryApi.summary(),
    enabled: !!facilityId,
    staleTime: 60_000,
  });

  if (dash.isLoading) return <LoadingState label="Loading your facility overview…" />;
  if (dash.error || !dash.data)
    return <ErrorState error={dash.error} onRetry={() => dash.refetch()} />;

  const d = dash.data;
  const items = inv.data?.items ?? [];
  const medicineUnits = items
    .filter((i) => i.category === "MEDICINE")
    .reduce((s, i) => s + i.usable_stock, 0);
  const vaccineUnits = items
    .filter((i) => i.category === "VACCINE")
    .reduce((s, i) => s + i.usable_stock, 0);
  const topStock = [...items]
    .sort((a, b) => b.usable_stock - a.usable_stock)
    .slice(0, 6)
    .map((i, idx) => ({
      label: i.product_name,
      value: i.usable_stock,
      color: CHART_COLORS[idx % CHART_COLORS.length],
      onClick: () => navigate("/inventory"),
    }));

  const lastMovement = d.data_freshness.last_stock_movement_at;
  const stale =
    !lastMovement ||
    Date.now() - new Date(lastMovement).getTime() > 7 * 86400000;

  const stockRole = canManageStock(user?.role);
  const vaccRole = canVaccinate(user?.role);
  const providesVacc = d.facility.provides_vaccination_services;

  const quickActions = [
    stockRole && { label: "Receive stock", icon: "package-check" as const, to: "/batches?action=receipt" },
    stockRole && { label: "Record wastage", icon: "trash" as const, to: "/batches?action=wastage" },
    canRequestTransfer(user?.role) && { label: "Request transfer", icon: "transfer" as const, to: "/transfers?new=1" },
    vaccRole && providesVacc && { label: "Register patient", icon: "user" as const, to: "/patients?new=1" },
    vaccRole && providesVacc && { label: "Record dose", icon: "syringe" as const, to: "/vaccination-records?new=1" },
  ].filter(Boolean) as { label: string; icon: "package-check" | "trash" | "transfer" | "user" | "syringe"; to: string }[];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Facility overview"
        title={d.facility.name}
        description={
          <>
            {d.facility.facility_type_display || humanize(d.facility.facility_type)} · {d.facility.region}
            {" · "}As of {formatDate(d.as_of)}
          </>
        }
        actions={
          <Button variant="secondary" icon="refresh" onClick={() => { dash.refetch(); inv.refetch(); }}>
            Refresh
          </Button>
        }
      />

      {stale && (
        <div className="alert alert-warning">
          <Icon name="clock" size={17} />
          <span>
            <strong>Data may be stale</strong>
            {lastMovement
              ? `Last stock activity was ${relativeTime(lastMovement)}. Record receipts and consumption to keep projections accurate.`
              : "No stock movements have been recorded yet. Receive stock to begin tracking."}
          </span>
        </div>
      )}

      <div className="stat-grid stagger">
        <StatCard label="Usable stock" value={formatNumber(d.inventory.usable_units)} sub="units across all products" icon="box" tone="teal" onClick={() => navigate("/inventory")} />
        <StatCard label="Active batches" value={formatNumber(d.inventory.total_batches)} sub="lot-level records" icon="layers" tone="blue" onClick={() => navigate("/batches")} />
        <StatCard label="Products with gap" value={formatNumber(d.inventory.products_with_gap)} sub="projected uncovered demand" icon="gap" tone="amber" onClick={() => navigate("/shortages")} />
        <StatCard label="Critical shortages" value={formatNumber(d.inventory.critical_shortages)} sub="need immediate action" icon="alert" tone="red" onClick={() => navigate("/shortages")} />
        <StatCard label="Vaccinations due (7d)" value={formatNumber(d.vaccinations.due_in_7_days)} sub={providesVacc ? "upcoming follow-ups" : "facility not vaccinating"} icon="syringe" tone="violet" onClick={vaccRole && providesVacc ? () => navigate("/followups?tab=due") : undefined} />
        <StatCard label="Overdue follow-ups" value={formatNumber(d.vaccinations.overdue)} sub="past due date" icon="clock" tone="red" onClick={vaccRole && providesVacc ? () => navigate("/followups?tab=overdue") : undefined} />
      </div>

      {quickActions.length > 0 && (
        <Card>
          <CardBody>
            <div className="row wrap" style={{ gap: 10 }}>
              <span className="faint" style={{ fontSize: 12.5, fontWeight: 600, marginRight: 4 }}>
                Quick actions
              </span>
              {quickActions.map((a) => (
                <Button key={a.label} variant="secondary" size="sm" icon={a.icon} onClick={() => navigate(a.to)}>
                  {a.label}
                </Button>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      <div className="grid-2-1">
        <Card>
          <CardHeader title="Usable stock by product" subtitle="Top products · click to open inventory" icon="box" />
          <CardBody>
            {inv.isLoading ? (
              <LoadingState label="Loading stock…" />
            ) : topStock.length === 0 ? (
              <EmptyState icon="box" title="No stock recorded" message="Receive your first batch to see stock levels here." />
            ) : (
              <BarChart data={topStock} formatValue={(v) => formatNumber(v)} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Stock mix" subtitle="Usable units by category" icon="pill" />
          <CardBody>
            {medicineUnits + vaccineUnits === 0 ? (
              <EmptyState icon="pill" title="Nothing in stock" />
            ) : (
              <DonutChart
                data={[
                  { label: "Medicines", value: medicineUnits, color: CHART_COLORS[1] },
                  { label: "Vaccines", value: vaccineUnits, color: CHART_COLORS[0] },
                ]}
                centerLabel="total units"
                centerValue={formatNumber(medicineUnits + vaccineUnits)}
              />
            )}
            <div className="divider" />
            <div className="detail-grid">
              <div className="detail-item">
                <div className="dt">Equipment</div>
                <div className="dd">{formatNumber(d.equipment.total)} assets</div>
              </div>
              <div className="detail-item">
                <div className="dt">Out of service</div>
                <div className="dd" style={{ color: d.equipment.out_of_service ? "var(--red)" : undefined }}>
                  {formatNumber(d.equipment.out_of_service)}
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Projected shortages"
            subtitle="Uncovered demand over the horizon"
            icon="gap"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/shortages")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody>
            {d.shortages.length === 0 ? (
              <EmptyState icon="check-circle" title="No projected shortages" message="Every product with known demand is covered." />
            ) : (
              <BarChart
                data={d.shortages.slice(0, 8).map((s) => ({
                  label: s.product_name,
                  value: s.projected_gap ?? 0,
                  color: "var(--red)",
                  onClick: () => navigate("/shortages"),
                }))}
                formatValue={(v) => formatNumber(v)}
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Near-expiry batches"
            subtitle="Prioritize for use or redistribution"
            icon="clock"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/expiring")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody tight>
            {d.near_expiry.length === 0 ? (
              <EmptyState icon="check-circle" title="No near-expiry stock" message="No usable batches expire within the warning window." />
            ) : (
              <div>
                {d.near_expiry.slice(0, 6).map((b) => (
                  <button key={b.batch_id} className="dropdown-item" onClick={() => navigate("/expiring")}>
                    <span className="dropdown-icon" style={{ background: "var(--amber-050)", color: "var(--amber)" }}>
                      <Icon name="clock" size={16} />
                    </span>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className="cell-title truncate" style={{ display: "block" }}>{b.product_name}</span>
                      <span className="cell-sub" style={{ display: "block" }}>{b.batch_number} · {formatNumber(b.quantity_available)} units</span>
                    </span>
                    <Badge tone={b.days_until_expiry <= 30 ? "red" : "amber"} dot={false}>
                      {b.days_until_expiry}d left
                    </Badge>
                  </button>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Incoming transfers"
            subtitle="Shipments heading to this facility"
            icon="truck"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/transfers")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody tight>
            {d.transfers.incoming.length === 0 ? (
              <EmptyState icon="inbox" title="No incoming transfers" />
            ) : (
              d.transfers.incoming.slice(0, 6).map((t) => (
                <TransferRow key={t.id} t={t} onClick={() => navigate(`/transfers/${t.id}`)} />
              ))
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Outgoing transfers"
            subtitle="Stock leaving this facility"
            icon="transfer"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/transfers")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody tight>
            {d.transfers.outgoing.length === 0 ? (
              <EmptyState icon="inbox" title="No outgoing transfers" />
            ) : (
              d.transfers.outgoing.slice(0, 6).map((t) => (
                <TransferRow key={t.id} t={t} onClick={() => navigate(`/transfers/${t.id}`)} />
              ))
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Recent stock movements"
          subtitle={`Last activity ${relativeTime(lastMovement)}`}
          icon="activity"
          action={<Button variant="ghost" size="sm" onClick={() => navigate("/movements")}>Full ledger <Icon name="arrow-right" size={14} /></Button>}
        />
        <CardBody>
          {d.recent_movements.length === 0 ? (
            <EmptyState icon="activity" title="No movements yet" message="Receipts, consumption and transfers will appear here." />
          ) : (
            <div className="timeline">
              {d.recent_movements.slice(0, 8).map((m) => <MovementRow key={m.id} m={m} />)}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
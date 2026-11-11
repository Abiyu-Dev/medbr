import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { DashboardApi } from "@/api/endpoints";
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
import { CHART_COLORS, TONE_HEX, toneFor } from "@/lib/status";
import { formatDate, formatNumber, humanize, relativeTime } from "@/lib/formatters";

export function CentralDashboard() {
  const navigate = useNavigate();
  const dash = useQuery({
    queryKey: ["dashboard", "central"],
    queryFn: () => DashboardApi.central(),
    refetchInterval: 60_000,
  });

  if (dash.isLoading) return <LoadingState label="Loading network overview…" />;
  if (dash.error || !dash.data)
    return <ErrorState error={dash.error} onRetry={() => dash.refetch()} />;

  const d = dash.data;
  const sg = d.supply_gaps;
  const activeGaps = sg.open + sg.under_review + sg.assigned + sg.action_planned + sg.escalated;

  const gapStatusData = [
    { label: "Open", value: sg.open, color: TONE_HEX.red },
    { label: "Assigned", value: sg.assigned + sg.under_review, color: TONE_HEX.blue },
    { label: "Action planned", value: sg.action_planned, color: TONE_HEX.violet },
    { label: "Escalated", value: sg.escalated, color: TONE_HEX.amber },
    { label: "Resolved / closed", value: sg.resolved + sg.closed, color: TONE_HEX.green },
  ].filter((x) => x.value > 0);

  const transferPipeline = [
    { label: "Requested", value: d.transfers.requested, color: CHART_COLORS[1], onClick: () => navigate("/transfers?status=REQUESTED") },
    { label: "Approved", value: d.transfers.approved, color: CHART_COLORS[0], onClick: () => navigate("/transfers?status=APPROVED") },
    { label: "Dispatched", value: d.transfers.dispatched, color: CHART_COLORS[3], onClick: () => navigate("/transfers?status=DISPATCHED") },
    { label: "In transit", value: d.transfers.in_transit, color: CHART_COLORS[2], onClick: () => navigate("/transfers?status=IN_TRANSIT") },
    { label: "Received", value: d.transfers.received, color: CHART_COLORS[5], onClick: () => navigate("/transfers?status=RECEIVED") },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Central coordination"
        title="Network overview"
        description={`Cross-facility supply, transfers and vaccination demand · as of ${formatDate(d.as_of)}`}
        actions={
          <>
            <Button variant="secondary" icon="map" onClick={() => navigate("/map")}>Facility map</Button>
            <Button variant="secondary" icon="refresh" onClick={() => dash.refetch()}>Refresh</Button>
          </>
        }
      />

      <div className="stat-grid stagger">
        <StatCard label="Approved facilities" value={formatNumber(d.facilities.approved)} sub={`${d.facilities.suspended} suspended`} icon="building" tone="teal" onClick={() => navigate("/facilities")} />
        <StatCard label="Pending applications" value={formatNumber(d.facilities.pending_applications)} sub="awaiting review" icon="clipboard" tone="amber" onClick={() => navigate("/applications")} />
        <StatCard label="Critical supply gaps" value={formatNumber(sg.critical_active)} sub={`${sg.high_active} high priority`} icon="gap" tone="red" onClick={() => navigate("/supply-gaps?priority=CRITICAL")} />
        <StatCard label="Transfers to review" value={formatNumber(d.transfers.requested)} sub={`${d.transfers.recent_7d} in last 7 days`} icon="transfer" tone="blue" onClick={() => navigate("/transfers?status=REQUESTED")} />
        <StatCard label="AI awaiting review" value={formatNumber(d.ai_recommendations.pending_review)} sub={`${d.ai_recommendations.failed_last_7_days} failed this week`} icon="sparkles" tone="violet" onClick={() => navigate("/ai?status=PENDING_REVIEW")} />
        <StatCard label="Overdue vaccinations" value={formatNumber(d.vaccinations.overdue)} sub={`${d.vaccinations.due_7d} due in 7 days`} icon="syringe" tone="red" />
      </div>

      <Card>
        <CardBody>
          <div className="row wrap" style={{ gap: 10 }}>
            <span className="faint" style={{ fontSize: 12.5, fontWeight: 600, marginRight: 4 }}>Quick actions</span>
            <Button variant="secondary" size="sm" icon="clipboard" onClick={() => navigate("/applications")}>Review applications</Button>
            <Button variant="secondary" size="sm" icon="gap" onClick={() => navigate("/supply-gaps")}>Supply gaps</Button>
            <Button variant="secondary" size="sm" icon="transfer" onClick={() => navigate("/transfers")}>Transfers</Button>
            <Button variant="secondary" size="sm" icon="sparkles" onClick={() => navigate("/ai")}>AI recommendations</Button>
            <Button variant="secondary" size="sm" icon="box" onClick={() => navigate("/inventory")}>Nationwide stock</Button>
          </div>
        </CardBody>
      </Card>

      <div className="grid-2-1">
        <Card>
          <CardHeader
            title="Highest uncovered demand"
            subtitle="Top supply gaps · click to open the queue"
            icon="gap"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/supply-gaps")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody>
            {d.top_gaps.length === 0 ? (
              <EmptyState icon="check-circle" title="No active supply gaps" message="Refresh the gap reports to recompute nationwide shortages." action={<Button size="sm" icon="refresh" onClick={() => navigate("/supply-gaps")}>Open supply gaps</Button>} />
            ) : (
              <BarChart
                data={d.top_gaps.slice(0, 8).map((g) => ({
                  label: `${g.product_name} · ${g.facility_name}`,
                  value: g.uncovered_quantity,
                  color: TONE_HEX[toneFor(g.priority)],
                  onClick: () => navigate("/supply-gaps"),
                }))}
                formatValue={(v) => formatNumber(v)}
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Gap status" subtitle={`${activeGaps} active reports`} icon="audit" />
          <CardBody>
            {gapStatusData.length === 0 ? (
              <EmptyState icon="check-circle" title="No gap reports" />
            ) : (
              <DonutChart data={gapStatusData} centerLabel="active" centerValue={formatNumber(activeGaps)} />
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader title="Transfer pipeline" subtitle="Click a stage to filter transfers" icon="transfer" />
          <CardBody>
            <BarChart data={transferPipeline} formatValue={(v) => formatNumber(v)} />
            <div className="divider" />
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Phone-arranged</div><div className="dd">{formatNumber(d.deliveries.arranged_by_phone)}</div></div>
              <div className="detail-item"><div className="dt">Discrepancies</div><div className="dd" style={{ color: d.deliveries.discrepancy ? "var(--amber)" : undefined }}>{formatNumber(d.deliveries.discrepancy)}</div></div>
              <div className="detail-item"><div className="dt">Failed deliveries</div><div className="dd" style={{ color: d.deliveries.failed ? "var(--red)" : undefined }}>{formatNumber(d.deliveries.failed)}</div></div>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Nationwide stock" subtitle="Usable units by category" icon="box" />
          <CardBody>
            {d.stock.medicine_units + d.stock.vaccine_units === 0 ? (
              <EmptyState icon="box" title="No stock recorded" />
            ) : (
              <DonutChart
                data={[
                  { label: "Medicines", value: d.stock.medicine_units, color: CHART_COLORS[1] },
                  { label: "Vaccines", value: d.stock.vaccine_units, color: CHART_COLORS[0] },
                ]}
                centerLabel="total units"
                centerValue={formatNumber(d.stock.medicine_units + d.stock.vaccine_units)}
              />
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Near-expiry redistribution"
            subtitle="Surplus batches that could cover a gap"
            icon="clock"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/transfers?new=1")}>New transfer <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody tight>
            {d.near_expiry_redistribution.length === 0 ? (
              <EmptyState icon="check-circle" title="No redistribution candidates" message="No near-expiry surplus batches across the network." />
            ) : (
              d.near_expiry_redistribution.slice(0, 6).map((b) => (
                <button
                  key={b.batch_id}
                  className="dropdown-item"
                  onClick={() => navigate(`/transfers?new=1&product=${b.product_id}&source=${b.facility_id}`)}
                >
                  <span className="dropdown-icon" style={{ background: "var(--amber-050)", color: "var(--amber)" }}>
                    <Icon name="clock" size={16} />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className="cell-title truncate" style={{ display: "block" }}>{b.product_name} · {formatNumber(b.quantity_available)} units</span>
                    <span className="cell-sub truncate" style={{ display: "block" }}>{b.facility_name} · {b.batch_number}</span>
                  </span>
                  <Badge tone={b.days_until_expiry <= 30 ? "red" : "amber"} dot={false}>{b.days_until_expiry}d</Badge>
                </button>
              ))
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="AI review queue"
            subtitle="Advisory analyses awaiting a human decision"
            icon="sparkles"
            action={<Button variant="ghost" size="sm" onClick={() => navigate("/ai")}>View all <Icon name="arrow-right" size={14} /></Button>}
          />
          <CardBody tight>
            {d.ai_recommendations.queue.length === 0 ? (
              <EmptyState icon="sparkles" title="Queue is clear" message="No AI recommendations are awaiting review." />
            ) : (
              d.ai_recommendations.queue.slice(0, 6).map((q) => (
                <button key={q.id} className="dropdown-item" onClick={() => navigate(`/ai/${q.id}`)}>
                  <span className="dropdown-icon" style={{ background: "var(--violet-050)", color: "var(--violet)" }}>
                    <Icon name="sparkles" size={16} />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className="cell-title truncate" style={{ display: "block" }}>{humanize(q.analysis_type)}</span>
                    <span className="cell-sub truncate" style={{ display: "block" }}>
                      {q.scope_facility_name || "Nationwide"} · {relativeTime(q.created_at)}
                      {q.validation_error_count > 0 && ` · ${q.validation_error_count} validation note(s)`}
                    </span>
                  </span>
                  <Icon name="chevron-right" size={16} style={{ color: "var(--faint)" }} />
                </button>
              ))
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AIApi, SupplyGapsApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Priority, SupplyGapReport } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { Badge, Button, Card, DataTable, Drawer, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, Tabs, TextArea, TextInput, useToast, type Column } from "@/components/ui";
import { FacilitySelect } from "@/components/forms/Pickers";
import { formatDate, formatNumber, humanize } from "@/lib/formatters";

const TABS = [
  { key: "", label: "All" },
  { key: "OPEN", label: "Open" },
  { key: "ASSIGNED", label: "Assigned" },
  { key: "ESCALATED", label: "Escalated" },
  { key: "RESOLVED", label: "Resolved" },
  { key: "CLOSED", label: "Closed" },
];
const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const TERMINAL = ["RESOLVED", "CLOSED"];

type GapAction = "assign" | "escalate" | "resolve";

function GapActionModal({
  action,
  gap,
  onClose,
  onDone,
}: {
  action: GapAction;
  gap: SupplyGapReport;
  onClose: () => void;
  onDone: (g: SupplyGapReport) => void;
}) {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [mode, setMode] = useState<"me" | "other">("me");
  const [otherId, setOtherId] = useState("");
  const [note, setNote] = useState("");
  const [finalStatus, setFinalStatus] = useState<"RESOLVED" | "CLOSED">("RESOLVED");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const assignedTo = mode === "me" ? user?.id : Number(otherId);
  const mutation = useMutation({
    mutationFn: () => {
      if (action === "assign") return SupplyGapsApi.assign(gap.id, assignedTo as number, note.trim() || undefined);
      if (action === "escalate") return SupplyGapsApi.escalate(gap.id, note.trim() || undefined);
      return SupplyGapsApi.resolve(gap.id, note.trim(), finalStatus);
    },
    onSuccess: (data) => {
      const label = action === "assign" ? "Gap assigned" : action === "escalate" ? "Gap escalated" : "Gap resolved";
      toast.success(label, `${data.product_name} · ${data.facility_name}`);
      qc.invalidateQueries({ queryKey: ["supply-gaps"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone(data);
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Action failed", e.detail); }
      else toast.error("Action failed", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid =
    action === "assign"
      ? Number.isInteger(assignedTo) && (assignedTo as number) > 0
      : action === "resolve"
        ? note.trim() !== ""
        : true;

  const title = action === "assign" ? "Assign gap" : action === "escalate" ? "Escalate gap" : "Resolve gap";
  const confirm = action === "assign" ? "Assign" : action === "escalate" ? "Escalate" : "Resolve";

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      subtitle={`${gap.product_name} · ${gap.facility_name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button variant={action === "escalate" ? "danger" : "primary"} loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{confirm}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {action === "assign" && (
          <>
            <Field label="Coordinator" error={fe("assigned_to")}>
              <SelectInput value={mode} onChange={(e) => setMode(e.target.value as "me" | "other")}>
                <option value="me">Assign to me — {user?.username}</option>
                <option value="other">Another coordinator (user ID)</option>
              </SelectInput>
            </Field>
            {mode === "other" && (
              <Field label="User ID" required error={fe("assigned_to")} help="The active user who will own this gap.">
                <TextInput type="number" min={1} step={1} value={otherId} onChange={(e) => setOtherId(e.target.value)} placeholder="e.g. 2" />
              </Field>
            )}
            <Field label="Note" error={fe("note")} help="Optional — appended to the gap summary.">
              <TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Will coordinate transport…" />
            </Field>
          </>
        )}
        {action === "escalate" && (
          <>
            <div className="alert alert-warning"><Icon name="alert" size={16} /><span>Escalating flags this gap for urgent central attention.</span></div>
            <Field label="Escalation note" error={fe("note")} help="Optional — appended to the gap summary.">
              <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this needs escalation…" />
            </Field>
          </>
        )}
        {action === "resolve" && (
          <>
            <Field label="Final status" error={fe("final_status")}>
              <SelectInput value={finalStatus} onChange={(e) => setFinalStatus(e.target.value as "RESOLVED" | "CLOSED")}>
                <option value="RESOLVED">Resolved — shortage covered</option>
                <option value="CLOSED">Closed — no longer relevant</option>
              </SelectInput>
            </Field>
            <Field label="Resolution notes" required error={fe("resolution_notes")}>
              <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="How was this gap covered?" invalid={!!fe("resolution_notes")} />
            </Field>
            <div className="alert alert-info"><Icon name="info" size={16} /><span>A future refresh will open a new report if the shortage still exists.</span></div>
          </>
        )}
      </div>
    </Modal>
  );
}

function GapDrawer({
  gap: initial,
  onClose,
  onPlan,
  planning,
}: {
  gap: SupplyGapReport;
  onClose: () => void;
  onPlan: () => void;
  planning: boolean;
}) {
  const [gap, setGap] = useState(initial);
  const [action, setAction] = useState<GapAction | null>(null);
  const terminal = TERMINAL.includes(gap.status);
  const covered = gap.usable_stock + gap.reliable_incoming_quantity;
  const coverPct = gap.projected_demand > 0 ? Math.min(100, Math.round((covered / gap.projected_demand) * 100)) : 100;

  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title={gap.product_name}
      subtitle={`${gap.facility_name} · ${humanize(gap.product_category)}`}
      footer={
        !terminal ? (
          <>
            <Button variant="secondary" icon="ban" onClick={() => setAction("resolve")}>Resolve</Button>
            {gap.status !== "ESCALATED" && <Button variant="danger" icon="trend-up" onClick={() => setAction("escalate")}>Escalate</Button>}
            <Button icon="user" onClick={() => setAction("assign")}>Assign</Button>
            {gap.uncovered_quantity > 0 && (
              <Button icon="sparkles" loading={planning} onClick={onPlan}>Plan with AI</Button>
            )}
          </>
        ) : <Button variant="secondary" onClick={onClose}>Close</Button>
      }
    >
      <div className="stack" style={{ gap: 18 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <Badge value={gap.status}>{gap.status_display}</Badge>
          <Badge value={gap.priority} dot={false}>{gap.priority_display}</Badge>
          {gap.assigned_to_username && <span className="chip"><Icon name="user" size={13} /> {gap.assigned_to_username}</span>}
        </div>

        {gap.active_request && (
          <div className="row wrap" style={{ gap: 8 }}>
            <span className="chip"><Icon name="truck" size={13} /> Request #{gap.active_request.id} · {gap.active_request.status_display} · {formatNumber(gap.active_request.quantity)} units</span>
            {gap.active_request.proposal_status && <span className="chip"><Icon name="sparkles" size={13} /> Proposal {humanize(gap.active_request.proposal_status)}</span>}
            {gap.active_request.transfer_id && (
              <Link to={`/transfers/${gap.active_request.transfer_id}`} className="chip"><Icon name="trend-up" size={13} /> Transfer #{gap.active_request.transfer_id}</Link>
            )}
          </div>
        )}

        <div className="alert alert-danger" style={{ alignItems: "center" }}>
          <Icon name="gap" size={20} />
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 24, fontWeight: 700, lineHeight: 1.1 }}>{formatNumber(gap.uncovered_quantity)} <span style={{ fontSize: 13, fontWeight: 500 }}>units uncovered</span></div>
            <div style={{ fontSize: 12.5, marginTop: 2 }}>Projected demand {formatNumber(gap.projected_demand)} over the reporting horizon.</div>
          </div>
        </div>

        <div>
          <div className="row-between" style={{ fontSize: 12.5, marginBottom: 6 }}>
            <span className="muted">Coverage from stock + reliable incoming</span>
            <strong>{coverPct}%</strong>
          </div>
          <div style={{ height: 10, borderRadius: 999, background: "var(--surface-3)", overflow: "hidden" }}>
            <div style={{ width: `${coverPct}%`, height: "100%", background: coverPct >= 100 ? "var(--lime)" : coverPct >= 50 ? "var(--amber)" : "var(--red)", borderRadius: 999, transition: "width .4s ease" }} />
          </div>
        </div>

        <div className="detail-grid">
          <div className="detail-item"><div className="dt">Projected demand</div><div className="dd">{formatNumber(gap.projected_demand)}</div></div>
          <div className="detail-item"><div className="dt">Usable stock</div><div className="dd">{formatNumber(gap.usable_stock)}</div></div>
          <div className="detail-item"><div className="dt">Reliable incoming</div><div className="dd">{formatNumber(gap.reliable_incoming_quantity)}</div></div>
          <div className="detail-item"><div className="dt">Uncovered</div><div className="dd" style={{ color: "var(--red)" }}>{formatNumber(gap.uncovered_quantity)}</div></div>
          <div className="detail-item"><div className="dt">Horizon start</div><div className="dd">{formatDate(gap.reporting_horizon_start)}</div></div>
          <div className="detail-item"><div className="dt">Horizon end</div><div className="dd">{formatDate(gap.reporting_horizon_end)}</div></div>
          <div className="detail-item"><div className="dt">Assigned to</div><div className="dd">{gap.assigned_to_username || "Unassigned"}</div></div>
          <div className="detail-item"><div className="dt">Resolved at</div><div className="dd">{formatDate(gap.resolved_at)}</div></div>
        </div>

        {gap.reason_summary && (
          <div className="detail-item"><div className="dt">Reason summary</div><div className="dd" style={{ fontWeight: 400, lineHeight: 1.6, whiteSpace: "pre-line" }}>{gap.reason_summary}</div></div>
        )}
        {gap.resolution_notes && (
          <div className="detail-item"><div className="dt">Resolution notes</div><div className="dd" style={{ fontWeight: 400, lineHeight: 1.6 }}>{gap.resolution_notes}</div></div>
        )}
      </div>
      {action && <GapActionModal action={action} gap={gap} onClose={() => setAction(null)} onDone={setGap} />}
    </Drawer>
  );
}

export function SupplyGapsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initialStatus = params.get("status") ?? "";
  const initialPriority = params.get("priority") ?? "";
  const initialFacility = params.get("facility") ?? "";
  const [tab, setTab] = useState(initialStatus);
  const list = useList<SupplyGapReport>(
    ["supply-gaps"],
    SupplyGapsApi.list,
    { status: initialStatus, priority: initialPriority, facility: initialFacility },
  );
  const [selected, setSelected] = useState<SupplyGapReport | null>(null);

  useEffect(() => {
    if (params.get("status") || params.get("priority") || params.get("facility")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useMutation({
    mutationFn: () => SupplyGapsApi.refresh(),
    onSuccess: (data) => {
      toast.success("Supply gaps refreshed", `${data.created} created · ${data.updated} updated · ${data.active_count} active`);
      qc.invalidateQueries({ queryKey: ["supply-gaps"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error("Refresh failed", isApiError(e) ? e.detail : "Something went wrong."),
  });

  const plan = useMutation({
    mutationFn: (gapIds?: number[]) =>
      AIApi.planGapSourcing(gapIds ? { gap_ids: gapIds } : {}),
    onSuccess: (rec) => {
      const created = rec.proposals_created ?? 0;
      if (rec.status === "FAILED") {
        toast.error("Sourcing analysis failed", rec.error || "The AI service was unavailable.");
      } else if (created > 0) {
        toast.success("Sourcing plan ready", `${created} transfer proposal(s) awaiting review on Supply requests.`);
      } else {
        toast.info("No proposals", "The AI could not cover these gaps from current surplus — see the recommendation.");
      }
      qc.invalidateQueries({ queryKey: ["supply-gaps"] });
      qc.invalidateQueries({ queryKey: ["supply-requests"] });
      qc.invalidateQueries({ queryKey: ["sourcing-proposals"] });
      qc.invalidateQueries({ queryKey: ["ai-recommendations"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/ai/${rec.id}`);
    },
    onError: (e) => toast.error("Planning failed", isApiError(e) ? e.detail : "Something went wrong."),
  });

  function changeTab(key: string) {
    setTab(key);
    list.setFilter("status", key);
  }

  const columns: Column<SupplyGapReport>[] = [
    {
      key: "product",
      header: "Product / Facility",
      render: (g) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{g.product_name}</span>
          <span className="cell-sub">{g.facility_name}</span>
        </div>
      ),
    },
    {
      key: "uncovered",
      header: "Uncovered",
      align: "right",
      sortField: "uncovered_quantity",
      render: (g) => <strong style={{ color: "var(--red)", fontSize: 15 }}>{formatNumber(g.uncovered_quantity)}</strong>,
    },
    {
      key: "demand",
      header: "Demand / Stock",
      align: "right",
      render: (g) => <span className="muted mono" style={{ fontSize: 12.5 }}>{formatNumber(g.projected_demand)} / {formatNumber(g.usable_stock)}</span>,
    },
    { key: "priority", header: "Priority", sortField: "priority", render: (g) => <Badge value={g.priority} dot={false}>{g.priority_display}</Badge> },
    { key: "status", header: "Status", render: (g) => <Badge value={g.status}>{g.status_display}</Badge> },
    { key: "assigned", header: "Assigned", render: (g) => g.assigned_to_username || <span className="faint">Unassigned</span> },
    { key: "horizon", header: "Horizon end", sortField: "created_at", render: (g) => formatDate(g.reporting_horizon_end) },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Central · Coordination"
        title="Supply gaps"
        description="Network-wide shortages computed from projected demand, usable stock and reliable incoming transfers."
        actions={
          <>
            <Button icon="sparkles" loading={plan.isPending && plan.variables === undefined} onClick={() => plan.mutate(undefined)}>Plan all open with AI</Button>
            <Button icon="refresh" loading={refresh.isPending} onClick={() => refresh.mutate()}>Refresh gaps</Button>
          </>
        }
      />
      <div className="alert alert-info">
        <Icon name="info" size={16} />
        <span><strong>Plan with AI</strong> asks the AI who can donate stock for each open gap, then routes its proposals to Supply requests for your approval — the chosen donor facility must also approve before the transfer dispatches. Receipt auto-resolves the gap.</span>
      </div>
      <Tabs items={TABS} active={tab} onChange={changeTab} />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search product, facility or reason…" />
          <SelectInput value={list.filters.priority ?? ""} onChange={(e) => list.setFilter("priority", e.target.value)} style={{ width: "auto" }}>
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
          </SelectInput>
          <div style={{ minWidth: 180, flex: "0 1 220px" }}>
            <FacilitySelect value={list.filters.facility ? Number(list.filters.facility) : ""} onChange={(v) => list.setFilter("facility", v === "" ? "" : String(v))} placeholder="All facilities" />
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(g) => g.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(g) => setSelected(g)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "gap", title: "No supply gaps", message: "No shortages match these filters. Refresh to recompute the network.", action: <Button icon="refresh" loading={refresh.isPending} onClick={() => refresh.mutate()}>Refresh gaps</Button> }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {selected && (
        <GapDrawer
          gap={selected}
          onClose={() => setSelected(null)}
          onPlan={() => plan.mutate([selected.id])}
          planning={plan.isPending && plan.variables !== undefined}
        />
      )}
    </div>
  );
}
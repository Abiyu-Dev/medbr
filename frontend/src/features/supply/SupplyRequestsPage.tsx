import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { SourcingApi, SupplyRequestsApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { SourcingProposal, SupplyRequest } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import { useList } from "@/hooks/useList";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Field,
  Icon,
  Modal,
  PageHeader,
  SearchBox,
  Tabs,
  TextArea,
  useToast,
  type Column,
} from "@/components/ui";
import { formatDate, formatNumber, humanize } from "@/lib/formatters";

const REQUEST_TABS = [
  { key: "", label: "All" },
  { key: "OPEN", label: "Open" },
  { key: "PLANNED", label: "Planned" },
  { key: "FULFILLED", label: "Fulfilled" },
  { key: "CANCELLED", label: "Cancelled" },
];
const PROPOSAL_TABS = [
  { key: "PROPOSED", label: "Awaiting review" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
];

function CancelRequestModal({
  request,
  onClose,
}: {
  request: SupplyRequest;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: () => SupplyRequestsApi.cancel(request.id, reason.trim() || undefined),
    onSuccess: () => {
      toast.success("Supply request cancelled", `${request.product_name} · ${request.facility_name}`);
      qc.invalidateQueries({ queryKey: ["supply-requests"] });
      onClose();
    },
    onError: (e) =>
      toast.error("Cancel failed", isApiError(e) ? e.detail : "Something went wrong."),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title="Cancel supply request"
      subtitle={`${request.product_name} · ${request.facility_name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Keep request</Button>
          <Button variant="danger" loading={mutation.isPending} onClick={() => mutation.mutate()}>Cancel request</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="alert alert-warning">
          <Icon name="alert" size={16} />
          <span>The central coordination team will no longer see this as an active need.</span>
        </div>
        <Field label="Reason" help="Optional — appended to the request for the audit trail.">
          <TextArea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Stock arrived from another route…" />
        </Field>
      </div>
    </Modal>
  );
}

function ProposalActionModal({
  action,
  proposal,
  onClose,
}: {
  action: "approve" | "reject";
  proposal: SourcingProposal;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      action === "approve"
        ? SourcingApi.approve(proposal.id, note.trim() || undefined)
        : SourcingApi.reject(proposal.id, note.trim()),
    onSuccess: (data) => {
      if (action === "approve") {
        toast.success(
          "Proposal approved — transfer requested",
          `Transfer #${data.transfer_id} sent to ${proposal.source_facility_name} for approval`,
        );
      } else {
        toast.success("Proposal rejected", `${proposal.product_name} · ${proposal.source_facility_name}`);
      }
      qc.invalidateQueries({ queryKey: ["sourcing-proposals"] });
      qc.invalidateQueries({ queryKey: ["supply-requests"] });
      qc.invalidateQueries({ queryKey: ["transfers"] });
      qc.invalidateQueries({ queryKey: ["ai-recommendations"] });
      onClose();
    },
    onError: (e) =>
      toast.error("Action failed", isApiError(e) ? e.detail : "Something went wrong."),
  });
  const valid = action === "approve" || note.trim() !== "";

  return (
    <Modal
      open
      onClose={onClose}
      title={action === "approve" ? "Approve sourcing proposal" : "Reject sourcing proposal"}
      subtitle={`${formatNumber(proposal.quantity)} ${proposal.product_name} · ${proposal.source_facility_name} → ${proposal.requesting_facility_name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Back</Button>
          <Button
            variant={action === "approve" ? "success" : "danger"}
            loading={mutation.isPending}
            disabled={!valid}
            onClick={() => mutation.mutate()}
          >
            {action === "approve" ? "Approve & request transfer" : "Reject proposal"}
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {action === "approve" ? (
          <div className="alert alert-info">
            <Icon name="info" size={16} />
            <span>
              Approving creates a real transfer request from <strong>{proposal.source_facility_name}</strong> to{" "}
              <strong>{proposal.requesting_facility_name}</strong>. The transfer only moves once the source facility
              approves it; central then dispatches.
            </span>
          </div>
        ) : (
          <div className="alert alert-warning">
            <Icon name="alert" size={16} />
            <span>Other proposals for the same request stay open for review.</span>
          </div>
        )}
        <Field label={action === "approve" ? "Review note" : "Rejection reason"} required={action === "reject"} error={undefined}>
          <TextArea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={action === "approve" ? "Optional context for the audit trail…" : "Why is this source not suitable?"}
          />
        </Field>
      </div>
    </Modal>
  );
}

export function SupplyRequestsPage() {
  const { user } = useAuth();
  const central = isCentral(user?.role);
  const toast = useToast();
  const qc = useQueryClient();

  const [requestTab, setRequestTab] = useState("OPEN");
  const [lang, setLang] = useState<"en" | "am">("en");
  const requests = useList<SupplyRequest>(
    ["supply-requests"],
    SupplyRequestsApi.list,
    { status: "OPEN" },
  );
  const [proposalTab, setProposalTab] = useState("PROPOSED");
  const proposals = useList<SourcingProposal>(
    ["sourcing-proposals"],
    SourcingApi.proposals,
    { status: "PROPOSED" },
  );

  const [cancelTarget, setCancelTarget] = useState<SupplyRequest | null>(null);
  const [proposalAction, setProposalAction] = useState<{
    action: "approve" | "reject";
    proposal: SourcingProposal;
  } | null>(null);

  const plan = useMutation({
    mutationFn: (requestId?: number) =>
      SourcingApi.plan(
        requestId ? { supply_request_ids: [requestId] } : {},
      ),
    onSuccess: (rec) => {
      const created = rec.proposals_created ?? 0;
      if (rec.status === "FAILED") {
        toast.error("Sourcing analysis failed", rec.error || "The AI service was unavailable.");
      } else if (created > 0) {
        toast.success("Sourcing plan ready", `${created} transfer proposal(s) awaiting your review below.`);
      } else {
        toast.info("No proposals", "The AI could not fill these requests from current surplus — see the recommendation for details.");
      }
      qc.invalidateQueries({ queryKey: ["sourcing-proposals"] });
      qc.invalidateQueries({ queryKey: ["ai-recommendations"] });
    },
    onError: (e) =>
      toast.error("Planning failed", isApiError(e) ? e.detail : "Something went wrong."),
  });

  const hasAmharicReason = proposals.rows.some((p) => p.reason_amharic);
  const tr = (en: string, am?: string) => (lang === "am" && am ? am : en);

  const requestColumns: Column<SupplyRequest>[] = [
    {
      key: "product",
      header: "Product / Facility",
      render: (r) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{r.product_name}</span>
          <span className="cell-sub">{r.facility_name}</span>
        </div>
      ),
    },
    {
      key: "quantity",
      header: "Quantity requested",
      align: "right",
      render: (r) => (
        <strong style={{ fontSize: 15 }}>{formatNumber(r.quantity)} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>{humanize(r.unit_of_measure)}</span></strong>
      ),
    },
    { key: "status", header: "Status", render: (r) => <Badge value={r.status}>{r.status_display}</Badge> },
    { key: "requested_by", header: "Requested by", render: (r) => r.requested_by_username || <span className="faint">—</span> },
    { key: "created", header: "Created", sortField: "created_at", render: (r) => formatDate(r.created_at) },
    ...(central
      ? [
          {
            key: "proposals",
            header: "Proposals",
            render: (r: SupplyRequest) =>
              r.open_proposals_count > 0 ? (
                <span className="chip"><Icon name="sparkles" size={13} /> {r.open_proposals_count} open</span>
              ) : (
                <span className="faint">—</span>
              ),
          } as Column<SupplyRequest>,
        ]
      : []),
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
          {central && r.status === "OPEN" && (
            <Button
              size="sm"
              variant="secondary"
              icon="sparkles"
              loading={plan.isPending && plan.variables === r.id}
              onClick={() => plan.mutate(r.id)}
            >
              Plan with AI
            </Button>
          )}
          {!central && (r.status === "OPEN" || r.status === "PLANNED") && (
            <Button size="sm" variant="ghost" icon="ban" onClick={() => setCancelTarget(r)}>Cancel</Button>
          )}
        </div>
      ),
    },
  ];

  const proposalColumns: Column<SourcingProposal>[] = [
    {
      key: "route",
      header: "Source → Requester",
      render: (p) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{p.source_facility_name}</span>
          <span className="cell-sub">→ {p.requesting_facility_name}</span>
        </div>
      ),
    },
    {
      key: "product",
      header: "Product / Quantity",
      render: (p) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{p.product_name}</span>
          <span className="cell-sub">{formatNumber(p.quantity)} units · request #{p.request}</span>
        </div>
      ),
    },
    {
      key: "reason",
      header: "AI reason",
      render: (p) =>
        p.reason ? (
          <span style={{ fontSize: 12.5, lineHeight: 1.5, display: "block", maxWidth: 320 }}>{tr(p.reason, p.reason_amharic)}</span>
        ) : (
          <span className="faint">—</span>
        ),
    },
    { key: "status", header: "Status", render: (p) => <Badge value={p.status}>{p.status_display}</Badge> },
    {
      key: "transfer",
      header: "Transfer",
      render: (p) =>
        p.transfer_id ? (
          <Link to={`/transfers/${p.transfer_id}`} className="chip">#{p.transfer_id} · {humanize(p.transfer_status || "")}</Link>
        ) : (
          <span className="faint">—</span>
        ),
    },
    { key: "created", header: "Proposed", render: (p) => formatDate(p.created_at) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (p) =>
        p.status === "PROPOSED" ? (
          <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
            <Button size="sm" variant="ghost" icon="x" onClick={() => setProposalAction({ action: "reject", proposal: p })}>Reject</Button>
            <Button size="sm" icon="check" onClick={() => setProposalAction({ action: "approve", proposal: p })}>Approve</Button>
          </div>
        ) : (
          <span className="faint" style={{ fontSize: 12 }}>{p.reviewed_by_username ? `by ${p.reviewed_by_username}` : "—"}</span>
        ),
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow={central ? "Central · Coordination" : "Facility · Coordination"}
        title="Supply requests"
        description={
          central
            ? "Requests raised by facilities when they approve an AI inventory analysis. Plan donor transfers with AI, review each proposal, then approve or reject."
            : "Requests sent to the central system when your facility approves an AI analysis that recommends transfers. Central plans and coordinates the fulfilment."
        }
        actions={
          central ? (
            <Button
              icon="sparkles"
              loading={plan.isPending && plan.variables === undefined}
              onClick={() => plan.mutate(undefined)}
            >
              Plan all open with AI
            </Button>
          ) : undefined
        }
      />

      <div className="alert alert-info">
        <Icon name="info" size={16} />
        <span>
          {central
            ? "Approving a proposal creates a real transfer request to the chosen source facility. The transfer becomes shippable only after that facility approves it; you then dispatch and track it under Transfers."
            : "Approving your facility's AI inventory analysis automatically sends its transfer recommendations here as supply requests."}
        </span>
      </div>

      <Tabs items={REQUEST_TABS} active={requestTab} onChange={(k) => { setRequestTab(k); requests.setFilter("status", k); }} />
      <Card>
        <div className="toolbar">
          <SearchBox value={requests.search} onChange={requests.setSearch} placeholder="Search product or facility…" />
        </div>
        <DataTable
          columns={requestColumns}
          rows={requests.rows}
          rowKey={(r) => r.id}
          isLoading={requests.query.isLoading}
          error={requests.query.error}
          onRetry={() => requests.query.refetch()}
          ordering={requests.ordering}
          onSort={requests.setOrdering}
          empty={{ icon: "truck", title: "No supply requests", message: central ? "No facility requests match these filters." : "Approve an AI inventory analysis to send its transfer recommendations here." }}
          pagination={{ page: requests.page, count: requests.count, pageSize: requests.pageSize, onPageChange: requests.setPage }}
        />
      </Card>

      {central && (
        <>
          <PageHeader
            eyebrow="Central · AI sourcing"
            title="Transfer proposals"
            description="AI-planned donor transfers for open requests. Approve one to create the transfer; reject the alternatives."
            actions={
              hasAmharicReason ? (
                <div className="row" style={{ gap: 0, border: "1px solid var(--border)", borderRadius: 999, overflow: "hidden" }}>
                  {([["en", "English"], ["am", "አማርኛ"]] as const).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setLang(key)}
                      style={{ padding: "4px 12px", fontSize: 12.5, border: "none", cursor: "pointer", background: lang === key ? "var(--brand)" : "transparent", color: lang === key ? "#fff" : "var(--muted)", fontWeight: lang === key ? 600 : 400 }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              ) : undefined
            }
          />
          <Tabs items={PROPOSAL_TABS} active={proposalTab} onChange={(k) => { setProposalTab(k); proposals.setFilter("status", k); }} />
          <Card>
            <DataTable
              columns={proposalColumns}
              rows={proposals.rows}
              rowKey={(p) => p.id}
              isLoading={proposals.query.isLoading}
              error={proposals.query.error}
              onRetry={() => proposals.query.refetch()}
              empty={{ icon: "sparkles", title: "No proposals", message: "Run “Plan with AI” on an open request to generate donor transfer proposals." }}
              pagination={{ page: proposals.page, count: proposals.count, pageSize: proposals.pageSize, onPageChange: proposals.setPage }}
            />
          </Card>
        </>
      )}

      {cancelTarget && <CancelRequestModal request={cancelTarget} onClose={() => setCancelTarget(null)} />}
      {proposalAction && (
        <ProposalActionModal
          action={proposalAction.action}
          proposal={proposalAction.proposal}
          onClose={() => setProposalAction(null)}
        />
      )}
    </div>
  );
}

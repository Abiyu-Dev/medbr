import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AIApi } from "@/api/endpoints";
import type { AIAnalysisType, AIRecommendation } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useOwnFacility } from "@/hooks/useOwnFacility";
import { useList } from "@/hooks/useList";
import { canRunInventoryAI, canRunVaccinationAI, isCentral } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, Icon, PageHeader, SelectInput, Tabs, type Column, type IconName } from "@/components/ui";
import { FacilitySelect } from "@/components/forms/Pickers";
import { formatDate, humanize, relativeTime } from "@/lib/formatters";
import { AnalyzeModal } from "./AnalyzeModal";

const TABS = [
  { key: "", label: "All" },
  { key: "PENDING_REVIEW", label: "Pending review" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
  { key: "FAILED", label: "Failed" },
  { key: "INVALID", label: "Invalid" },
];
const TYPE_ICON: Record<AIAnalysisType, IconName> = {
  INVENTORY_ANALYSIS: "box",
  SUPPLY_GAP_PRIORITIZATION: "gap",
  VACCINATION_DEMAND_SUMMARY: "syringe",
  TRANSFER_SOURCING: "truck",
};
const TYPES: AIAnalysisType[] = ["INVENTORY_ANALYSIS", "SUPPLY_GAP_PRIORITIZATION", "VACCINATION_DEMAND_SUMMARY", "TRANSFER_SOURCING"];

export function AIPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const own = useOwnFacility();
  const central = isCentral(user?.role);
  const [params, setParams] = useSearchParams();
  const initialStatus = params.get("status") ?? "";
  const [tab, setTab] = useState(initialStatus);
  const list = useList<AIRecommendation>(["ai-recommendations"], AIApi.list, { status: initialStatus, analysis_type: "", scope_facility: "" }, "-created_at");
  const [analyze, setAnalyze] = useState(false);

  const canRunAny = canRunInventoryAI(user?.role) || central || (canRunVaccinationAI(user?.role) && own.providesVaccination);

  useEffect(() => {
    if (params.get("status")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeTab(key: string) {
    setTab(key);
    list.setFilter("status", key);
  }

  const columns: Column<AIRecommendation>[] = [
    {
      key: "type", header: "Analysis",
      render: (r) => (
        <div className="row" style={{ gap: 9 }}>
          <span style={{ color: "var(--brand)", display: "grid", placeItems: "center" }}><Icon name={TYPE_ICON[r.analysis_type]} size={17} /></span>
          <span className="cell-title" style={{ fontSize: 13 }}>{r.analysis_type_display || humanize(r.analysis_type)}</span>
        </div>
      ),
    },
    { key: "scope", header: "Scope", render: (r) => r.scope_facility_name || <span className="chip"><Icon name="globe" size={12} /> Nationwide</span> },
    {
      key: "summary", header: "Summary",
      render: (r) => r.summary
        ? <span className="muted" style={{ fontSize: 12.5, display: "block", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.summary}>{r.summary}</span>
        : <span className="faint" style={{ fontSize: 12.5 }}>{r.status === "FAILED" ? "Service unavailable" : "No summary"}</span>,
    },
    { key: "status", header: "Status", sortField: "status", render: (r) => <Badge value={r.status}>{r.status_display || humanize(r.status)}</Badge> },
    {
      key: "requested", header: "Requested", sortField: "created_at",
      render: (r) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-sub">{r.requested_by_username}</span>
          <span className="cell-sub">{relativeTime(r.created_at)}</span>
        </div>
      ),
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Advisory AI"
        title="AI recommendations"
        description="Gemini-assisted analysis, validated against live data. Every recommendation is advisory and requires human review — the AI never moves stock."
        actions={canRunAny && <Button icon="sparkles" onClick={() => setAnalyze(true)}>Run analysis</Button>}
      />
      <Tabs items={TABS} active={tab} onChange={changeTab} />
      <Card>
        <div className="toolbar">
          <SelectInput value={list.filters.analysis_type ?? ""} onChange={(e) => list.setFilter("analysis_type", e.target.value)} style={{ width: "auto" }}>
            <option value="">All analyses</option>
            {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </SelectInput>
          {central && (
            <div style={{ minWidth: 180, flex: "0 1 220px" }}>
              <FacilitySelect value={list.filters.scope_facility ? Number(list.filters.scope_facility) : ""} onChange={(v) => list.setFilter("scope_facility", v === "" ? "" : String(v))} placeholder="All scopes" />
            </div>
          )}
          <span className="muted" style={{ fontSize: 12.5, marginLeft: "auto" }}>{list.count} recommendation{list.count === 1 ? "" : "s"}</span>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(r) => r.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(r) => navigate(`/ai/${r.id}`)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "sparkles", title: "No recommendations", message: canRunAny ? "Run an analysis to generate an advisory recommendation." : "Recommendations shared with your facility will appear here.", action: canRunAny ? <Button icon="sparkles" onClick={() => setAnalyze(true)}>Run analysis</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {analyze && <AnalyzeModal onClose={() => setAnalyze(false)} />}
    </div>
  );
}
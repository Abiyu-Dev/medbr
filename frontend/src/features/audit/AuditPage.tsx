import { useState } from "react";
import { AuditApi } from "@/api/endpoints";
import type { AuditLog } from "@/api/types";
import { useList } from "@/hooks/useList";
import { useAuth } from "@/auth/AuthContext";
import { isCentral, ROLE_LABELS } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, Drawer, Icon, PageHeader, SearchBox, SelectInput, type Column } from "@/components/ui";
import { formatDateTime, humanize } from "@/lib/formatters";

const ENTITY_TYPES = [
  "Facility", "User", "Patient", "VaccinationRecord", "VaccineFollowUp", "VaccineSchedule",
  "StockBatch", "StockMovement", "TransferRequest", "DeliveryCoordination", "SupplyGapReport",
  "AIRecommendation", "System",
];

const ENTITY_LABELS: Record<string, string> = {
  Facility: "Facility",
  User: "User",
  Patient: "Patient",
  VaccinationRecord: "Vaccination Record",
  VaccineFollowUp: "Vaccine Follow-up",
  VaccineSchedule: "Vaccine Schedule",
  StockBatch: "Stock Batch",
  StockMovement: "Stock Movement",
  TransferRequest: "Transfer Request",
  DeliveryCoordination: "Delivery Coordination",
  SupplyGapReport: "Supply Gap Report",
  AIRecommendation: "AI Recommendation",
  System: "System",
};

const entityLabel = (type?: string | null) => (type ? ENTITY_LABELS[type] ?? type : "—");

function AuditDrawer({ log, onClose }: { log: AuditLog; onClose: () => void }) {
  const meta = log.metadata ?? {};
  const metaEntries = Object.entries(meta);
  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title={humanize(log.action)}
      subtitle={`${entityLabel(log.entity_type)} #${log.entity_id}`}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      <div className="stack" style={{ gap: 18 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <span className="chip mono"><Icon name="audit" size={13} /> {log.action}</span>
          <Badge tone="blue" dot={false}>{entityLabel(log.entity_type)}</Badge>
        </div>
        <div className="detail-grid">
          <div className="detail-item"><div className="dt">Actor</div><div className="dd">{log.actor_username || "System"}</div></div>
          <div className="detail-item"><div className="dt">Role</div><div className="dd">{log.actor_role ? ROLE_LABELS[log.actor_role] : "—"}</div></div>
          <div className="detail-item"><div className="dt">Facility</div><div className="dd">{log.actor_facility_name || "—"}</div></div>
          <div className="detail-item"><div className="dt">Timestamp</div><div className="dd">{formatDateTime(log.created_at)}</div></div>
          <div className="detail-item"><div className="dt">Entity</div><div className="dd">{entityLabel(log.entity_type)} #{log.entity_id}</div></div>
          <div className="detail-item"><div className="dt">IP address</div><div className="dd mono">{log.ip_address || "—"}</div></div>
        </div>
        <div>
          <div className="dt" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--faint)", fontWeight: 600, marginBottom: 8 }}>Metadata</div>
          {metaEntries.length === 0 ? (
            <div className="muted" style={{ fontSize: 13 }}>No additional metadata recorded.</div>
          ) : (
            <>
              <div className="detail-grid" style={{ marginBottom: 12 }}>
                {metaEntries.map(([k, v]) => (
                  <div className="detail-item" key={k}>
                    <div className="dt">{humanize(k)}</div>
                    <div className="dd mono" style={{ fontWeight: 400, fontSize: 13, wordBreak: "break-word" }}>{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                  </div>
                ))}
              </div>
              <pre className="code-block">{JSON.stringify(meta, null, 2)}</pre>
            </>
          )}
        </div>
      </div>
    </Drawer>
  );
}

const PATIENT_ENTITIES = new Set(["Patient", "VaccinationRecord", "VaccineFollowUp"]);

export function AuditPage() {
  const { user } = useAuth();
  const list = useList<AuditLog>(["audit"], AuditApi.list, { action: "", entity_type: "" }, "-created_at");
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const entityTypes = isCentral(user?.role)
    ? ENTITY_TYPES.filter((t) => !PATIENT_ENTITIES.has(t))
    : ENTITY_TYPES;

  const columns: Column<AuditLog>[] = [
    { key: "when", header: "Timestamp", sortField: "created_at", width: "170px", render: (l) => <span className="cell-sub">{formatDateTime(l.created_at)}</span> },
    {
      key: "actor", header: "Actor",
      render: (l) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title" style={{ fontSize: 13 }}>{l.actor_username || "System"}</span>
          <span className="cell-sub">{l.actor_role ? ROLE_LABELS[l.actor_role] : "—"}</span>
        </div>
      ),
    },
    { key: "action", header: "Action", render: (l) => <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{humanize(l.action)}</span> },
    {
      key: "entity", header: "Entity",
      render: (l) => (
        <div className="row" style={{ gap: 7 }}>
          <Badge tone="blue" dot={false}>{entityLabel(l.entity_type)}</Badge>
          <span className="cell-sub mono">#{l.entity_id}</span>
        </div>
      ),
    },
    { key: "facility", header: "Facility", render: (l) => l.actor_facility_name || <span className="faint">—</span> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="A read-only trail of every significant action. Visibility is scoped to your role — patient-level entries are hidden from central coordinators."
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search action, entity type or ID…" />
          <SelectInput value={list.filters.entity_type ?? ""} onChange={(e) => list.setFilter("entity_type", e.target.value)} style={{ width: "auto" }}>
            <option value="">All entities</option>
            {entityTypes.map((t) => <option key={t} value={t}>{entityLabel(t)}</option>)}
          </SelectInput>
          <span className="muted" style={{ fontSize: 12.5, marginLeft: "auto" }}>{list.count} entr{list.count === 1 ? "y" : "ies"}</span>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(l) => l.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(l) => setSelected(l)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "audit", title: "No audit entries", message: "Actions matching these filters will appear here." }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {selected && <AuditDrawer log={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
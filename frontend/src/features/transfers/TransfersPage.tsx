import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { TransfersApi } from "@/api/endpoints";
import type { Priority, TransferRequest } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canRequestTransfer } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, PageHeader, SearchBox, SelectInput, Tabs, type Column } from "@/components/ui";
import { formatDate, formatNumber, relativeTime } from "@/lib/formatters";
import { TransferFormModal } from "./TransferFormModal";

const TABS = [
  { key: "", label: "All" },
  { key: "REQUESTED", label: "Requested" },
  { key: "APPROVED", label: "Approved" },
  { key: "DISPATCHED", label: "Dispatched" },
  { key: "IN_TRANSIT", label: "In transit" },
  { key: "RECEIVED", label: "Received" },
];
const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function TransfersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initialStatus = params.get("status") ?? "";
  const [tab, setTab] = useState(initialStatus);
  const list = useList<TransferRequest>(["transfers"], TransfersApi.list, { status: initialStatus, priority: "" }, "-created_at");
  const [create, setCreate] = useState<{ product?: number; source?: number; destination?: number; quantity?: number } | null>(null);

  useEffect(() => {
    const newFlag = params.get("new");
    const product = params.get("product");
    const source = params.get("source");
    const dest = params.get("dest");
    const quantity = params.get("quantity");
    if (newFlag === "1") {
      setCreate({
        product: product ? Number(product) : undefined,
        source: source ? Number(source) : undefined,
        destination: dest ? Number(dest) : undefined,
        quantity: quantity ? Number(quantity) : undefined,
      });
    }
    if (newFlag || product || source || dest || quantity || params.get("status")) {
      setParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeTab(key: string) {
    setTab(key);
    list.setFilter("status", key);
  }

  const columns: Column<TransferRequest>[] = [
    {
      key: "product",
      header: "Product",
      render: (t) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{t.product_name}</span>
          <span className="cell-sub mono">{t.source_batch_number}</span>
        </div>
      ),
    },
    {
      key: "route",
      header: "Route",
      render: (t) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title" style={{ fontSize: 13 }}>{t.source_facility_name}</span>
          <span className="cell-sub">→ {t.destination_facility_name}</span>
        </div>
      ),
    },
    {
      key: "qty",
      header: "Quantity",
      align: "right",
      render: (t) => (
        <div className="stack" style={{ gap: 2, alignItems: "flex-end" }}>
          <strong>{formatNumber(t.quantity_requested)}</strong>
          {t.quantity_approved != null && t.quantity_approved > 0 && <span className="cell-sub">{formatNumber(t.quantity_approved)} approved</span>}
        </div>
      ),
    },
    { key: "priority", header: "Priority", render: (t) => <Badge value={t.priority} dot={false}>{t.priority_display}</Badge> },
    { key: "status", header: "Status", render: (t) => <Badge value={t.status}>{t.status_display}</Badge> },
    { key: "requested", header: "Requested", sortField: "created_at", render: (t) => <div className="stack" style={{ gap: 2 }}><span className="cell-sub">{t.requested_by_username}</span><span className="cell-sub">{relativeTime(t.created_at)}</span></div> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Coordination"
        title="Transfers"
        description="Stock movement between facilities, from request through dispatch to receipt."
        actions={canRequestTransfer(user?.role) && <Button icon="plus" onClick={() => setCreate({})}>New transfer</Button>}
      />
      <Tabs items={TABS} active={tab} onChange={changeTab} />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search product or facility…" />
          <SelectInput value={list.filters.priority ?? ""} onChange={(e) => list.setFilter("priority", e.target.value)} style={{ width: "auto" }}>
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p.charAt(0) + p.slice(1).toLowerCase()}</option>)}
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(t) => t.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(t) => navigate(`/transfers/${t.id}`)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "transfer", title: "No transfers", message: "Transfer requests between facilities will appear here.", action: canRequestTransfer(user?.role) ? <Button icon="plus" onClick={() => setCreate({})}>New transfer</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {create && <TransferFormModal prefill={create} onClose={() => setCreate(null)} />}
    </div>
  );
}
import { useState } from "react";
import { StockApi } from "@/api/endpoints";
import type { MovementType, StockMovement } from "@/api/types";
import { useList } from "@/hooks/useList";
import { Badge, Button, Card, DataTable, Drawer, PageHeader, SearchBox, SelectInput, type Column } from "@/components/ui";
import { formatDateTime, formatNumber, humanize, relativeTime } from "@/lib/formatters";

const TYPES: MovementType[] = ["RECEIPT", "CONSUMPTION", "VACCINATION_ADMINISTRATION", "TRANSFER_OUT", "TRANSFER_IN", "WASTAGE", "ADJUSTMENT", "RETURN"];

export function MovementsPage() {
  const list = useList<StockMovement>(["movements"], StockApi.movements, { movement_type: "", direction: "" }, "-occurred_at");
  const [detail, setDetail] = useState<StockMovement | null>(null);

  const columns: Column<StockMovement>[] = [
    {
      key: "when",
      header: "When",
      sortField: "occurred_at",
      render: (m) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{relativeTime(m.occurred_at)}</span>
          <span className="cell-sub">{formatDateTime(m.occurred_at)}</span>
        </div>
      ),
    },
    { key: "type", header: "Type", render: (m) => <Badge value={m.movement_type} dot={false}>{m.movement_type_display || humanize(m.movement_type)}</Badge> },
    {
      key: "product",
      header: "Product / batch",
      render: (m) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{m.product_name}</span>
          <span className="cell-sub mono">{m.batch_number}</span>
        </div>
      ),
    },
    {
      key: "qty",
      header: "Quantity",
      align: "right",
      render: (m) => (
        <strong style={{ color: m.direction === "IN" ? "var(--lime)" : "var(--amber)" }}>
          {m.direction === "IN" ? "+" : "−"}{formatNumber(m.quantity)}
        </strong>
      ),
    },
    { key: "by", header: "By", render: (m) => m.performed_by_username || "system" },
    { key: "facility", header: "Facility", render: (m) => <span className="cell-sub">{m.facility_name}</span> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Inventory"
        title="Stock movements"
        description="The immutable ledger of every receipt, consumption, transfer, wastage and adjustment."
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search batch, product or reason…" />
          <div className="row wrap" style={{ gap: 8 }}>
            <SelectInput value={list.filters.movement_type ?? ""} onChange={(e) => list.setFilter("movement_type", e.target.value)} style={{ width: "auto" }}>
              <option value="">All types</option>
              {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </SelectInput>
            <SelectInput value={list.filters.direction ?? ""} onChange={(e) => list.setFilter("direction", e.target.value)} style={{ width: "auto" }}>
              <option value="">In &amp; out</option>
              <option value="IN">In only</option>
              <option value="OUT">Out only</option>
            </SelectInput>
            {(list.search || list.filters.movement_type || list.filters.direction) && (
              <Button variant="ghost" size="sm" icon="x" onClick={list.reset}>Clear</Button>
            )}
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(m) => m.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={setDetail}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "activity", title: "No movements yet", message: "Stock activity will appear here as it is recorded." }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>

      <Drawer open={!!detail} onClose={() => setDetail(null)} title="Movement detail" subtitle={detail ? `#${detail.id}` : ""}>
        {detail && (
          <div className="stack">
            <div className="row wrap" style={{ gap: 8 }}>
              <Badge value={detail.movement_type} dot={false}>{detail.movement_type_display || humanize(detail.movement_type)}</Badge>
              <Badge value={detail.direction} dot={false} />
            </div>
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Product</div><div className="dd">{detail.product_name}</div></div>
              <div className="detail-item"><div className="dt">Batch</div><div className="dd mono">{detail.batch_number}</div></div>
              <div className="detail-item"><div className="dt">Quantity</div><div className="dd">{detail.direction === "IN" ? "+" : "−"}{formatNumber(detail.quantity)}</div></div>
              <div className="detail-item"><div className="dt">Facility</div><div className="dd">{detail.facility_name}</div></div>
              <div className="detail-item"><div className="dt">Occurred</div><div className="dd">{formatDateTime(detail.occurred_at)}</div></div>
              <div className="detail-item"><div className="dt">Performed by</div><div className="dd">{detail.performed_by_username || "system"}</div></div>
              {detail.reference_type && <div className="detail-item"><div className="dt">Reference</div><div className="dd">{detail.reference_type} {detail.reference_id}</div></div>}
              {detail.idempotency_key && <div className="detail-item"><div className="dt">Idempotency key</div><div className="dd mono" style={{ fontSize: 11 }}>{detail.idempotency_key}</div></div>}
            </div>
            {detail.reason && <div className="detail-item"><div className="dt">Reason</div><div className="dd">{detail.reason}</div></div>}
          </div>
        )}
      </Drawer>
    </div>
  );
}
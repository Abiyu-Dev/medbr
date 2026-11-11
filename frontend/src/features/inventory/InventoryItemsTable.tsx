import type { InventoryItemSummary } from "@/api/types";
import { Badge, DataTable, type Column } from "@/components/ui";
import { formatNumber } from "@/lib/formatters";

function dash(v: number | null): string {
  return v === null || v === undefined ? "—" : formatNumber(v);
}

export function InventoryItemsTable({
  items,
  isLoading,
  error,
  onRetry,
  emptyTitle = "No stock recorded",
  emptyMessage = "Receive stock to build the inventory summary.",
}: {
  items: InventoryItemSummary[];
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyMessage?: string;
}) {
  const columns: Column<InventoryItemSummary>[] = [
    {
      key: "product",
      header: "Product",
      render: (i) => (
        <div className="stack" style={{ gap: 3 }}>
          <span className="cell-title">{i.product_name}</span>
          <span className="row" style={{ gap: 6 }}>
            <Badge value={i.category} dot={false} />
            <span className="cell-sub">{i.unit_of_measure}</span>
          </span>
        </div>
      ),
    },
    { key: "usable", header: "Usable", align: "right", render: (i) => <strong>{formatNumber(i.usable_stock)}</strong> },
    { key: "reserved", header: "Reserved", align: "right", render: (i) => formatNumber(i.reserved_stock) },
    { key: "incoming", header: "Incoming", align: "right", render: (i) => formatNumber(i.incoming_stock) },
    { key: "demand", header: "Proj. demand", align: "right", render: (i) => dash(i.projected_demand) },
    {
      key: "gap",
      header: "Gap",
      align: "right",
      render: (i) =>
        i.projected_gap === null ? (
          <span className="muted">—</span>
        ) : i.projected_gap > 0 ? (
          <Badge tone="red" dot={false}>{formatNumber(i.projected_gap)}</Badge>
        ) : (
          <span style={{ color: "var(--lime)" }}>0</span>
        ),
    },
    {
      key: "days",
      header: "Days of stock",
      align: "right",
      render: (i) => {
        if (i.days_of_stock === null) return <span className="muted">—</span>;
        const tone = i.days_of_stock <= 7 ? "var(--red)" : i.days_of_stock <= 30 ? "var(--amber)" : "var(--ink)";
        return <span style={{ color: tone, fontWeight: 600 }}>{formatNumber(i.days_of_stock)}</span>;
      },
    },
    {
      key: "near",
      header: "Near expiry",
      align: "right",
      render: (i) => i.near_expiry_quantity > 0 ? <Badge tone="amber" dot={false}>{formatNumber(i.near_expiry_quantity)}</Badge> : <span className="muted">0</span>,
    },
    { key: "batches", header: "Batches", align: "right", render: (i) => formatNumber(i.batch_count) },
  ];
  return (
    <DataTable
      columns={columns}
      rows={items}
      rowKey={(i) => i.product_id}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      empty={{ icon: "box", title: emptyTitle, message: emptyMessage }}
    />
  );
}
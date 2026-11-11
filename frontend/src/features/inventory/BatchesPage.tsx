import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BatchesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { StockBatch, StorageStatus } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canAdjustStock, canManageStock } from "@/lib/permissions";
import { daysUntil, formatDate, formatNumber } from "@/lib/formatters";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Drawer,
  Field,
  Icon,
  Modal,
  PageHeader,
  SearchBox,
  SelectInput,
  TextArea,
  TextInput,
  useToast,
  type Column,
} from "@/components/ui";
import { StockOpModal, type StockOpMode } from "./StockOpModal";

const STORAGE_OPTIONS: StorageStatus[] = ["OK", "QUARANTINED", "TEMPERATURE_EXCURSION", "DAMAGED", "EXPIRED"];

function ExpiryCell({ date }: { date: string }) {
  const days = daysUntil(date);
  const tone = days === null ? "slate" : days < 0 ? "slate" : days <= 30 ? "red" : days <= 90 ? "amber" : "green";
  return (
    <div className="stack" style={{ gap: 3 }}>
      <span>{formatDate(date)}</span>
      {days !== null && (
        <Badge tone={tone} dot={false}>
          {days < 0 ? "expired" : `${days}d left`}
        </Badge>
      )}
    </div>
  );
}

function BatchStatusModal({ batch, onClose }: { batch: StockBatch; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [status, setStatus] = useState<StorageStatus>(batch.storage_status);
  const [ref, setRef] = useState(batch.source_reference);
  const [err, setErr] = useState("");
  const mutation = useMutation({
    mutationFn: () => BatchesApi.update(batch.id, { storage_status: status, source_reference: ref }),
    onSuccess: () => {
      toast.success("Batch updated", `${batch.batch_number} storage status saved.`);
      qc.invalidateQueries({ queryKey: ["batches"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (e) => {
      const msg = isApiError(e) ? e.detail : "Could not update batch.";
      setErr(msg);
      toast.error("Update failed", msg);
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title="Update batch status"
      subtitle={`${batch.batch_number} · ${batch.product_name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>Save</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="alert alert-info">
          <Icon name="info" size={16} />
          <span>Quantities are immutable. To change stock levels, record a receipt, consumption, wastage or adjustment.</span>
        </div>
        <Field label="Storage status" required>
          <SelectInput value={status} onChange={(e) => setStatus(e.target.value as StorageStatus)}>
            {STORAGE_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </SelectInput>
        </Field>
        <Field label="Source reference">
          <TextInput value={ref} onChange={(e) => setRef(e.target.value)} placeholder="Supplier / donor reference" />
        </Field>
        {err && <div className="field-error"><Icon name="alert" size={13} />{err}</div>}
      </div>
    </Modal>
  );
}

export function BatchesPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const list = useList<StockBatch>(["batches"], BatchesApi.list, { storage_status: "" }, "-received_at");
  const [op, setOp] = useState<{ mode: StockOpMode; batchId?: number } | null>(null);
  const [detail, setDetail] = useState<StockBatch | null>(null);
  const [editStatus, setEditStatus] = useState<StockBatch | null>(null);

  const stockRole = canManageStock(user?.role);
  const adjustRole = canAdjustStock(user?.role);

  useEffect(() => {
    const action = params.get("action");
    if (action === "receipt" || action === "wastage" || action === "consumption" || action === "adjustment") {
      setOp({ mode: action });
      params.delete("action");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<StockBatch>[] = [
    {
      key: "batch",
      header: "Batch",
      render: (b) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title mono">{b.batch_number}</span>
          <span className="cell-sub">{b.product_name}</span>
        </div>
      ),
    },
    { key: "category", header: "Type", render: (b) => <Badge value={b.product_category} dot={false} /> },
    {
      key: "available",
      header: "Available",
      align: "right",
      sortField: "quantity_available",
      render: (b) => (
        <div className="stack" style={{ gap: 2, alignItems: "flex-end" }}>
          <strong>{formatNumber(b.quantity_available)}</strong>
          <span className="cell-sub">of {formatNumber(b.quantity_received)} received</span>
        </div>
      ),
    },
    { key: "reserved", header: "Reserved", align: "right", render: (b) => formatNumber(b.quantity_reserved) },
    { key: "expiry", header: "Expiry", sortField: "expiry_date", render: (b) => <ExpiryCell date={b.expiry_date} /> },
    { key: "status", header: "Storage", render: (b) => <Badge value={b.storage_status} /> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (b) => (
        <div className="row" style={{ gap: 4, justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
          {stockRole && (
            <Button variant="ghost" size="sm" icon="trend-down" title="Record consumption" onClick={() => setOp({ mode: "consumption", batchId: b.id })} />
          )}
          {stockRole && (
            <Button variant="ghost" size="sm" icon="trash" title="Record wastage" onClick={() => setOp({ mode: "wastage", batchId: b.id })} />
          )}
          {adjustRole && (
            <Button variant="ghost" size="sm" icon="settings" title="Adjust balance" onClick={() => setOp({ mode: "adjustment", batchId: b.id })} />
          )}
          {stockRole && (
            <Button variant="ghost" size="sm" icon="edit" title="Update storage status" onClick={() => setEditStatus(b)} />
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Inventory"
        title="Stock batches"
        description="Lot-level stock with expiry and storage status. Quantities change only through recorded movements."
        actions={stockRole && <Button icon="package-check" onClick={() => setOp({ mode: "receipt" })}>Receive stock</Button>}
      />

      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search batch or product…" />
          <div className="row wrap" style={{ gap: 8 }}>
            <SelectInput value={list.filters.storage_status ?? ""} onChange={(e) => list.setFilter("storage_status", e.target.value)} style={{ width: "auto" }}>
              <option value="">All storage statuses</option>
              {STORAGE_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </SelectInput>
            {(list.search || list.filters.storage_status) && (
              <Button variant="ghost" size="sm" icon="x" onClick={list.reset}>Clear</Button>
            )}
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(b) => b.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(b) => setDetail(b)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "layers", title: "No batches yet", message: "Receive your first stock batch to start tracking inventory.", action: stockRole ? <Button icon="package-check" onClick={() => setOp({ mode: "receipt" })}>Receive stock</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>

      {op && (
        <StockOpModal mode={op.mode} presetBatchId={op.batchId} onClose={() => setOp(null)} />
      )}
      {editStatus && <BatchStatusModal batch={editStatus} onClose={() => setEditStatus(null)} />}

      <Drawer open={!!detail} onClose={() => setDetail(null)} title={detail?.batch_number ?? ""} subtitle={detail?.product_name}>
        {detail && (
          <div className="stack">
            <div className="row wrap" style={{ gap: 8 }}>
              <Badge value={detail.product_category} dot={false} />
              <Badge value={detail.storage_status} />
              {detail.is_expired && <Badge tone="slate">Expired</Badge>}
            </div>
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Available</div><div className="dd">{formatNumber(detail.quantity_available)} {detail.product_name && ""}</div></div>
              <div className="detail-item"><div className="dt">Received</div><div className="dd">{formatNumber(detail.quantity_received)}</div></div>
              <div className="detail-item"><div className="dt">Reserved</div><div className="dd">{formatNumber(detail.quantity_reserved)}</div></div>
              <div className="detail-item"><div className="dt">Expiry</div><div className="dd">{formatDate(detail.expiry_date)}</div></div>
              <div className="detail-item"><div className="dt">Received at</div><div className="dd">{formatDate(detail.received_at)}</div></div>
              <div className="detail-item"><div className="dt">Facility</div><div className="dd">{detail.facility_name}</div></div>
            </div>
            {detail.source_reference && (
              <div className="detail-item"><div className="dt">Source reference</div><div className="dd">{detail.source_reference}</div></div>
            )}
            {stockRole && (
              <>
                <div className="divider" />
                <div className="row wrap" style={{ gap: 8 }}>
                  <Button variant="secondary" size="sm" icon="trend-down" onClick={() => { setOp({ mode: "consumption", batchId: detail.id }); setDetail(null); }}>Consume</Button>
                  <Button variant="secondary" size="sm" icon="trash" onClick={() => { setOp({ mode: "wastage", batchId: detail.id }); setDetail(null); }}>Wastage</Button>
                  {adjustRole && <Button variant="secondary" size="sm" icon="settings" onClick={() => { setOp({ mode: "adjustment", batchId: detail.id }); setDetail(null); }}>Adjust</Button>}
                  <Button variant="secondary" size="sm" icon="edit" onClick={() => { setEditStatus(detail); setDetail(null); }}>Status</Button>
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
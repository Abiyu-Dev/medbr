import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { TransfersApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import {
  canApproveTransfer,
  canCancelTransfer,
  canConfirmReceipt,
  canDispatch,
  canRejectTransfer,
  isCentral,
} from "@/lib/permissions";
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, Icon, LoadingState, PageHeader } from "@/components/ui";
import { formatDate, formatDateTime, formatNumber, humanize } from "@/lib/formatters";
import { TransferActionModal, type TransferAction } from "./TransferActionModal";
import { DeliveryCoordinationPanel } from "./DeliveryCoordination";

const STAGES = [
  { key: "REQUESTED", label: "Requested", icon: "clipboard" as const },
  { key: "APPROVED", label: "Approved", icon: "check" as const },
  { key: "DISPATCHED", label: "Dispatched", icon: "truck" as const },
  { key: "RECEIVED", label: "Received", icon: "package-check" as const },
];

const STAGE_INDEX: Record<string, number> = {
  DRAFT: 0, REQUESTED: 0, UNDER_REVIEW: 0,
  APPROVED: 1, DISPATCHED: 2, IN_TRANSIT: 2, RECEIVED: 3,
};

export function TransferDetailPage() {
  const { id } = useParams();
  const transferId = Number(id);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [action, setAction] = useState<TransferAction | null>(null);

  const q = useQuery({
    queryKey: ["transfer", transferId],
    queryFn: () => TransfersApi.get(transferId),
    enabled: Number.isFinite(transferId),
  });

  if (q.isLoading) return <LoadingState label="Loading transfer…" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const t = q.data;

  const canApprove = canApproveTransfer(user, t);
  const canReject = canRejectTransfer(user, t);
  const allowDispatch = canDispatch(user, t);
  const canReceipt = canConfirmReceipt(user, t);
  const canCancel = canCancelTransfer(user, t);
  const canCoordinate = isCentral(user?.role) || user?.facility === t.source_facility || user?.facility === t.destination_facility;
  const terminalNegative = ["REJECTED", "CANCELLED", "FAILED"].includes(t.status);
  const stageIndex = STAGE_INDEX[t.status] ?? 0;
  const received = t.status === "RECEIVED";
  const stageTimes = [t.created_at, t.approved_at, null, t.received_at];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Coordination · Transfer"
        title={t.product_name}
        description={`Transfer #${t.id} · ${t.source_facility_name} → ${t.destination_facility_name}`}
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            <Button variant="ghost" icon="chevron-left" onClick={() => navigate("/transfers")}>All transfers</Button>
            {canApprove && <Button variant="success" icon="check" onClick={() => setAction("approve")}>Approve</Button>}
            {allowDispatch && <Button icon="truck" onClick={() => setAction("dispatch")}>Dispatch</Button>}
            {canReceipt && <Button variant="success" icon="package-check" onClick={() => setAction("receipt")}>Confirm receipt</Button>}
            {canReject && <Button variant="danger" icon="x" onClick={() => setAction("reject")}>Reject</Button>}
            {canCancel && <Button variant="secondary" icon="ban" onClick={() => setAction("cancel")}>Cancel</Button>}
          </div>
        }
      />

      <Card>
        <CardBody>
          <div className="row-between wrap" style={{ gap: 12, marginBottom: 18 }}>
            <div className="row wrap" style={{ gap: 8 }}>
              <Badge value={t.status}>{t.status_display}</Badge>
              <Badge value={t.priority} dot={false}>{t.priority_display}</Badge>
              <span className="chip"><Icon name={t.product_name ? "pill" : "box"} size={13} /> {formatNumber(t.quantity_requested)} requested</span>
            </div>
            <span className="muted mono" style={{ fontSize: 12.5 }}>#{t.id}</span>
          </div>
          <div className="transfer-route">
            <div className="route-node source">
              <div className="route-role"><Icon name="building" size={13} /> Source</div>
              <div className="route-name">{t.source_facility_name}</div>
              <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>Batch <span className="mono">{t.source_batch_number || "—"}</span></div>
              {t.source_batch_expiry && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>Expiry {formatDate(t.source_batch_expiry)}</div>}
            </div>
            <div className="route-arrow">
              <span className="route-qty">{formatNumber(t.quantity_approved && t.quantity_approved > 0 ? t.quantity_approved : t.quantity_requested)}</span>
              <Icon name="arrow-right" size={24} />
              <span className="route-unit">units</span>
            </div>
            <div className="route-node dest">
              <div className="route-role"><Icon name="pin" size={13} /> Destination</div>
              <div className="route-name">{t.destination_facility_name}</div>
              <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
                {t.quantity_received !== null ? <><strong style={{ color: "var(--brand-700)" }}>{formatNumber(t.quantity_received)}</strong> received</> : "Awaiting receipt"}
              </div>
              {t.condition_on_receipt && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>Condition: {humanize(t.condition_on_receipt)}</div>}
            </div>
          </div>
        </CardBody>
      </Card>

      {t.status === "REJECTED" && (
        <div className="alert alert-danger"><Icon name="x-circle" size={17} /><span><strong>Rejected.</strong> {t.rejection_reason || "No reason was provided."}</span></div>
      )}
      {t.status === "CANCELLED" && (
        <div className="alert alert-warning"><Icon name="ban" size={17} /><span><strong>Cancelled.</strong> Any reserved stock has been released back to the source batch.</span></div>
      )}
      {t.status === "FAILED" && (
        <div className="alert alert-danger"><Icon name="alert" size={17} /><span><strong>Failed.</strong> This transfer could not be completed. Review the delivery log and audit trail.</span></div>
      )}

      {!terminalNegative && (
        <Card>
          <CardHeader title="Lifecycle" subtitle="Request → approval → dispatch → receipt" icon="activity" />
          <CardBody>
            <div className="stepper">
              {STAGES.map((s, i) => {
                const done = i < stageIndex || (received && i === stageIndex);
                const current = !received && i === stageIndex;
                return (
                  <div key={s.key} className={`step ${done ? "done" : current ? "current" : ""}`}>
                    <div className="step-dot"><Icon name={done ? "check" : s.icon} size={16} /></div>
                    <div className="step-label">{s.label}</div>
                    {stageTimes[i] && <div className="step-time">{formatDate(stageTimes[i])}</div>}
                  </div>
                );
              })}
            </div>
          </CardBody>
        </Card>
      )}

      <div className="grid-2-1">
        <Card>
          <CardHeader title="Transfer details" icon="clipboard" />
          <CardBody>
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Requested by</div><div className="dd">{t.requested_by_username || "—"}</div></div>
              <div className="detail-item"><div className="dt">Requested at</div><div className="dd">{formatDateTime(t.created_at)}</div></div>
              <div className="detail-item"><div className="dt">Quantity requested</div><div className="dd">{formatNumber(t.quantity_requested)}</div></div>
              <div className="detail-item"><div className="dt">Quantity approved</div><div className="dd">{t.quantity_approved && t.quantity_approved > 0 ? formatNumber(t.quantity_approved) : "—"}</div></div>
              <div className="detail-item"><div className="dt">Approved by</div><div className="dd">{t.approved_by_username || "—"}</div></div>
              <div className="detail-item"><div className="dt">Approved at</div><div className="dd">{formatDateTime(t.approved_at)}</div></div>
              <div className="detail-item"><div className="dt">Quantity received</div><div className="dd">{formatNumber(t.quantity_received)}</div></div>
              <div className="detail-item"><div className="dt">Received at</div><div className="dd">{formatDateTime(t.received_at)}</div></div>
              <div className="detail-item"><div className="dt">Condition on receipt</div><div className="dd">{t.condition_on_receipt ? humanize(t.condition_on_receipt) : "—"}</div></div>
              <div className="detail-item"><div className="dt">Expected dispatch</div><div className="dd">{formatDateTime(t.expected_dispatch_at)}</div></div>
              <div className="detail-item"><div className="dt">Expected arrival</div><div className="dd">{formatDateTime(t.expected_arrival_at)}</div></div>
              <div className="detail-item"><div className="dt">Last updated</div><div className="dd">{formatDateTime(t.updated_at)}</div></div>
            </div>
            {t.notes && (
              <div className="detail-item" style={{ marginTop: 16 }}><div className="dt">Notes</div><div className="dd" style={{ fontWeight: 400, lineHeight: 1.6 }}>{t.notes}</div></div>
            )}
          </CardBody>
        </Card>

        <DeliveryCoordinationPanel transferId={t.id} canAdd={canCoordinate} />
      </div>

      {action && <TransferActionModal action={action} transfer={t} onClose={() => setAction(null)} />}
    </div>
  );
}
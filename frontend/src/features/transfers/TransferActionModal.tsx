import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { TransfersApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { TransferRequest } from "@/api/types";
import { Button, Field, Icon, Modal, SelectInput, TextArea, TextInput, useToast } from "@/components/ui";
import { formatNumber } from "@/lib/formatters";

export type TransferAction = "approve" | "reject" | "dispatch" | "receipt" | "cancel";

const CONFIG: Record<
  TransferAction,
  { title: string; confirm: string; variant: "primary" | "danger" | "success"; icon: "check" | "x" | "truck" | "package-check" | "ban"; success: string }
> = {
  approve: { title: "Approve transfer", confirm: "Approve", variant: "success", icon: "check", success: "Transfer approved" },
  reject: { title: "Reject transfer", confirm: "Reject request", variant: "danger", icon: "x", success: "Transfer rejected" },
  dispatch: { title: "Dispatch transfer", confirm: "Confirm dispatch", variant: "primary", icon: "truck", success: "Transfer dispatched" },
  receipt: { title: "Confirm receipt", confirm: "Confirm receipt", variant: "success", icon: "package-check", success: "Receipt confirmed" },
  cancel: { title: "Cancel transfer", confirm: "Cancel transfer", variant: "danger", icon: "ban", success: "Transfer cancelled" },
};

const CONDITIONS = [
  { value: "OK", label: "OK — usable" },
  { value: "DAMAGED", label: "Damaged" },
  { value: "TEMPERATURE_EXCURSION", label: "Temperature excursion" },
];

export function TransferActionModal({
  action,
  transfer,
  onClose,
}: {
  action: TransferAction;
  transfer: TransferRequest;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const cfg = CONFIG[action];
  const approvedQty = transfer.quantity_approved ?? transfer.quantity_requested;
  const [quantity, setQuantity] = useState(String(action === "receipt" ? approvedQty : transfer.quantity_requested));
  const [condition, setCondition] = useState("OK");
  const [text, setText] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () => {
      switch (action) {
        case "approve":
          return TransfersApi.approve(transfer.id, quantity.trim() ? Number(quantity) : undefined);
        case "reject":
          return TransfersApi.reject(transfer.id, text.trim());
        case "dispatch":
          return TransfersApi.dispatch(transfer.id, text.trim() || undefined);
        case "receipt":
          return TransfersApi.confirmReceipt(transfer.id, {
            quantity_received: Number(quantity),
            condition,
            notes: text.trim() || undefined,
          });
        case "cancel":
          return TransfersApi.cancel(transfer.id, text.trim() || undefined);
      }
    },
    onSuccess: (data) => {
      toast.success(cfg.success, `${data.product_name} · ${data.status_display ?? data.status}`);
      qc.invalidateQueries({ queryKey: ["transfer", transfer.id] });
      qc.invalidateQueries({ queryKey: ["transfers"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["batches"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) {
        setFieldErrors(e.fieldErrors ?? {});
        toast.error("Action failed", e.detail);
      } else toast.error("Action failed", "Something went wrong.");
    },
  });

  const fe = (k: string) => fieldErrors[k];
  const qty = Number(quantity);
  const valid =
    action === "reject"
      ? text.trim() !== ""
      : action === "approve"
        ? Number.isInteger(qty) && qty >= 1 && qty <= transfer.quantity_requested
        : action === "receipt"
          ? Number.isInteger(qty) && qty >= 1 && qty <= approvedQty
          : true;

  return (
    <Modal
      open
      onClose={onClose}
      title={cfg.title}
      subtitle={`${transfer.product_name} · ${transfer.source_facility_name} → ${transfer.destination_facility_name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button variant={cfg.variant} icon={cfg.icon} loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>
            {cfg.confirm}
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {action === "approve" && (
          <>
            <div className="alert alert-info">
              <Icon name="info" size={16} />
              <span>Approving reserves stock at <strong>{transfer.source_facility_name}</strong>. The source team can then dispatch.</span>
            </div>
            <Field label="Quantity to approve" error={fe("quantity_approved")} help={`Up to ${formatNumber(transfer.quantity_requested)} requested and the batch's free stock. Defaults to the full request.`}>
              <TextInput type="number" min={1} max={transfer.quantity_requested} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} invalid={!!fe("quantity_approved")} />
            </Field>
          </>
        )}

        {action === "reject" && (
          <>
            <div className="alert alert-danger">
              <Icon name="alert" size={16} />
              <span>This rejects the request. No stock is reserved. Your reason is shown to the requester and recorded in the audit log.</span>
            </div>
            <Field label="Rejection reason" required error={fe("rejection_reason")}>
              <TextArea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Why is this request being rejected?" invalid={!!fe("rejection_reason")} />
            </Field>
          </>
        )}

        {action === "dispatch" && (
          <>
            <div className="alert alert-info">
              <Icon name="truck" size={16} />
              <span>Dispatching logs a <strong>transfer out</strong> at {transfer.source_facility_name} and removes <strong>{formatNumber(approvedQty)}</strong> units from the source batch.</span>
            </div>
            <Field label="Dispatch notes" error={fe("notes")} help="Optional — carrier, vehicle, handling instructions.">
              <TextArea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="How is the stock being sent?" />
            </Field>
          </>
        )}

        {action === "receipt" && (
          <>
            <div className="alert alert-info">
              <Icon name="package-check" size={16} />
              <span>Confirming receipt logs a <strong>transfer in</strong> at {transfer.destination_facility_name} and adds the stock to a destination batch.</span>
            </div>
            <div className="field-row">
              <Field label="Quantity received" required error={fe("quantity_received")} help={`Up to ${formatNumber(approvedQty)} approved.`}>
                <TextInput type="number" min={1} max={approvedQty} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} invalid={!!fe("quantity_received")} />
              </Field>
              <Field label="Condition on receipt" error={fe("condition")}>
                <SelectInput value={condition} onChange={(e) => setCondition(e.target.value)}>
                  {CONDITIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </SelectInput>
              </Field>
            </div>
            {Number.isInteger(qty) && qty < approvedQty && (
              <div className="alert alert-warning">
                <Icon name="alert" size={16} />
                <span>Receiving fewer than {formatNumber(approvedQty)} approved units records a <strong>discrepancy</strong> in the audit log.</span>
              </div>
            )}
            {condition !== "OK" && (
              <div className="alert alert-warning">
                <Icon name="alert" size={16} />
                <span>The destination batch will be flagged <strong>{condition === "DAMAGED" ? "damaged" : "temperature excursion"}</strong> and held from usable stock.</span>
              </div>
            )}
            <Field label="Receipt notes" error={fe("notes")}>
              <TextArea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Optional notes on arrival…" />
            </Field>
          </>
        )}

        {action === "cancel" && (
          <>
            <div className="alert alert-warning">
              <Icon name="alert" size={16} />
              <span>Cancelling releases any reserved stock at the source. This cannot be undone.</span>
            </div>
            <Field label="Reason" error={fe("reason")} help="Optional — recorded in the audit log.">
              <TextArea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Why is this transfer being cancelled?" />
            </Field>
          </>
        )}
      </div>
    </Modal>
  );
}
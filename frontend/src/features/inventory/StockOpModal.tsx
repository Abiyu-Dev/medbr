import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { StockApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import {
  Button,
  Field,
  Modal,
  SelectInput,
  TextArea,
  TextInput,
  useToast,
} from "@/components/ui";
import { BatchSelect, ProductSelect } from "@/components/forms/Pickers";
import { todayISO } from "@/lib/formatters";

export type StockOpMode = "receipt" | "consumption" | "wastage" | "adjustment";

const TITLES: Record<StockOpMode, string> = {
  receipt: "Receive stock",
  consumption: "Record consumption",
  wastage: "Record wastage",
  adjustment: "Adjust balance",
};

const SUBTITLES: Record<StockOpMode, string> = {
  receipt: "Add a new batch or merge into an existing batch number.",
  consumption: "Reduce usable stock for dispensed or administered units.",
  wastage: "Dispose of broken, expired or quarantined units.",
  adjustment: "Correct a counted balance (managers and admins only).",
};

function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `mb-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function StockOpModal({
  mode,
  onClose,
  presetBatchId,
  presetProductId,
}: {
  mode: StockOpMode;
  onClose: () => void;
  presetBatchId?: number;
  presetProductId?: number;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [key] = useState(newKey);
  const [product, setProduct] = useState<number | "">(presetProductId ?? "");
  const [batch, setBatch] = useState<number | "">(presetBatchId ?? "");
  const [batchNumber, setBatchNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [quantity, setQuantity] = useState("");
  const [direction, setDirection] = useState<"IN" | "OUT">("IN");
  const [reason, setReason] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [refType, setRefType] = useState("");
  const [refId, setRefId] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: async () => {
      const qty = Number(quantity);
      const idempotency_key = key;
      if (mode === "receipt") {
        return StockApi.receipt({
          product,
          batch_number: batchNumber.trim(),
          expiry_date: expiry,
          quantity: qty,
          source_reference: sourceRef.trim(),
          idempotency_key,
        });
      }
      if (mode === "consumption") {
        return StockApi.consumption({
          batch,
          quantity: qty,
          reason: reason.trim(),
          reference_type: refType.trim() || undefined,
          reference_id: refId.trim() || undefined,
          idempotency_key,
        });
      }
      if (mode === "wastage") {
        return StockApi.wastage({ batch, quantity: qty, reason: reason.trim(), idempotency_key });
      }
      return StockApi.adjustment({ batch, quantity: qty, direction, reason: reason.trim(), idempotency_key });
    },
    onSuccess: (data) => {
      const replayed = "replayed" in data && data.replayed;
      if (replayed) toast.info("Already recorded", "This operation was already applied — no duplicate created.");
      else toast.success(TITLES[mode], mode === "receipt" ? "Batch received into stock." : "Stock movement recorded.");
      qc.invalidateQueries({ queryKey: ["batches"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["expiring"] });
      onClose();
    },
    onError: (err) => {
      if (isApiError(err)) {
        setFieldErrors(err.fieldErrors ?? {});
        toast.error("Could not record", err.detail);
      } else {
        toast.error("Could not record", "Something went wrong.");
      }
    },
  });

  const fe = (k: string) => fieldErrors[k];
  const qty = Number(quantity);
  const valid =
    quantity !== "" &&
    Number.isInteger(qty) &&
    qty > 0 &&
    (mode === "receipt"
      ? product !== "" && batchNumber.trim() !== "" && expiry !== ""
      : batch !== "") &&
    (mode === "wastage" || mode === "adjustment" ? reason.trim() !== "" : true);

  return (
    <Modal
      open
      onClose={onClose}
      title={TITLES[mode]}
      subtitle={SUBTITLES[mode]}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button
            variant={mode === "wastage" ? "danger" : "primary"}
            loading={mutation.isPending}
            disabled={!valid}
            onClick={() => mutation.mutate()}
          >
            {mode === "receipt" ? "Receive stock" : "Record"}
          </Button>
        </>
      }
    >
      <form
        className="stack"
        style={{ gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) mutation.mutate();
        }}
      >
        {mode === "receipt" ? (
          <>
            <Field label="Product" required error={fe("product")}>
              <ProductSelect value={product} onChange={setProduct} invalid={!!fe("product")} />
            </Field>
            <div className="field-row">
              <Field label="Batch number" required error={fe("batch_number")} help="Matching numbers merge into one batch.">
                <TextInput value={batchNumber} onChange={(e) => setBatchNumber(e.target.value)} placeholder="e.g. PARA-2601" invalid={!!fe("batch_number")} />
              </Field>
              <Field label="Expiry date" required error={fe("expiry_date")}>
                <TextInput type="date" value={expiry} min={todayISO()} onChange={(e) => setExpiry(e.target.value)} invalid={!!fe("expiry_date")} />
              </Field>
            </div>
            <div className="field-row">
              <Field label="Quantity" required error={fe("quantity")}>
                <TextInput type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="0" invalid={!!fe("quantity")} />
              </Field>
              <Field label="Source reference" error={fe("source_reference")}>
                <TextInput value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} placeholder="Supplier / donor" />
              </Field>
            </div>
          </>
        ) : (
          <>
            <Field label="Batch" required error={fe("batch")}>
              <BatchSelect
                value={batch}
                onChange={setBatch}
                usableOnly={mode === "consumption"}
                invalid={!!fe("batch")}
              />
            </Field>
            <div className="field-row">
              <Field label="Quantity" required error={fe("quantity")}>
                <TextInput type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="0" invalid={!!fe("quantity")} />
              </Field>
              {mode === "adjustment" && (
                <Field label="Direction" required error={fe("direction")}>
                  <SelectInput value={direction} onChange={(e) => setDirection(e.target.value as "IN" | "OUT")}>
                    <option value="IN">IN — add units</option>
                    <option value="OUT">OUT — remove units</option>
                  </SelectInput>
                </Field>
              )}
            </div>
            <Field
              label="Reason"
              required={mode === "wastage" || mode === "adjustment"}
              error={fe("reason")}
            >
              <TextArea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={mode === "wastage" ? "e.g. Broken vial during handling" : mode === "adjustment" ? "e.g. Physical recount correction" : "e.g. Dispensed to OPD"} invalid={!!fe("reason")} />
            </Field>
            {mode === "consumption" && (
              <div className="field-row">
                <Field label="Reference type" error={fe("reference_type")}>
                  <TextInput value={refType} onChange={(e) => setRefType(e.target.value)} placeholder="prescription" />
                </Field>
                <Field label="Reference ID" error={fe("reference_id")}>
                  <TextInput value={refId} onChange={(e) => setRefId(e.target.value)} placeholder="RX-001" />
                </Field>
              </div>
            )}
          </>
        )}
        <button type="submit" style={{ display: "none" }} aria-hidden />
      </form>
    </Modal>
  );
}
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { TransfersApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Priority } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import { Button, Field, Icon, Modal, SelectInput, TextArea, TextInput, useToast } from "@/components/ui";
import { BatchSelect, FacilitySelect, ProductSelect } from "@/components/forms/Pickers";
import { localInputToISO } from "@/lib/formatters";

const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function TransferFormModal({
  prefill,
  onClose,
}: {
  prefill?: { product?: number; source?: number; destination?: number; quantity?: number };
  onClose: () => void;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const central = isCentral(user?.role);
  const ownFacility = user?.facility ?? null;

  const [source, setSource] = useState<number | "">(central ? (prefill?.source ?? "") : (ownFacility ?? ""));
  const [destination, setDestination] = useState<number | "">(prefill?.destination ?? "");
  const [product, setProduct] = useState<number | "">(prefill?.product ?? "");
  const [batch, setBatch] = useState<number | "">("");
  const [quantity, setQuantity] = useState(prefill?.quantity ? String(prefill.quantity) : "");
  const [priority, setPriority] = useState<Priority>("MEDIUM");
  const [dispatch, setDispatch] = useState("");
  const [arrival, setArrival] = useState("");
  const [notes, setNotes] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () =>
      TransfersApi.create({
        source_facility: source,
        destination_facility: destination,
        product,
        source_batch: batch,
        quantity_requested: Number(quantity),
        priority,
        expected_dispatch_at: localInputToISO(dispatch) ?? null,
        expected_arrival_at: localInputToISO(arrival) ?? null,
        notes: notes.trim(),
      }),
    onSuccess: (data) => {
      toast.success("Transfer requested", `${data.product_name} · ${data.source_facility_name} → ${data.destination_facility_name}`);
      qc.invalidateQueries({ queryKey: ["transfers"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
      onClose();
      navigate(`/transfers/${data.id}`);
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not create transfer", e.detail); }
      else toast.error("Could not create transfer", "Something went wrong.");
    },
  });

  const fe = (k: string) => fieldErrors[k];
  const qty = Number(quantity);
  const valid =
    source !== "" && destination !== "" && source !== destination &&
    product !== "" && batch !== "" && Number.isInteger(qty) && qty > 0;

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="New transfer request"
      subtitle={central ? "Move stock between facilities in the network." : "Send stock from your facility to another facility."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Request transfer</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {!central && (
          <div className="alert alert-info">
            <Icon name="info" size={16} />
            <span>Stock leaves <strong>{user?.facility_name || "your facility"}</strong>. A coordinator or the source manager approves before dispatch. Central coordinators can arrange incoming resupply.</span>
          </div>
        )}
        <div className="field-row">
          <Field label="From (source)" required error={fe("source_facility")}>
            {central ? (
              <FacilitySelect value={source} onChange={(v) => { setSource(v); setBatch(""); }} excludeId={destination || null} invalid={!!fe("source_facility")} />
            ) : (
              <TextInput value={user?.facility_name || "Your facility"} disabled />
            )}
          </Field>
          <Field label="To (destination)" required error={fe("destination_facility")}>
            <FacilitySelect value={destination} onChange={setDestination} excludeId={source || null} invalid={!!fe("destination_facility")} network={!central} placeholder={central ? "Select facility…" : "Select destination facility…"} />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Product" required error={fe("product")}>
            <ProductSelect value={product} onChange={(v) => { setProduct(v); setBatch(""); }} invalid={!!fe("product")} />
          </Field>
          <Field label="Priority" error={fe("priority")}>
            <SelectInput value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p.charAt(0) + p.slice(1).toLowerCase()}</option>)}
            </SelectInput>
          </Field>
        </div>
        <Field label="Source batch" required error={fe("source_batch")} help="Only usable batches with free stock are listed.">
          <BatchSelect value={batch} onChange={setBatch} productId={product} facilityId={source} central={central} usableOnly invalid={!!fe("source_batch")} />
        </Field>
        <Field label="Quantity requested" required error={fe("quantity_requested")}>
          <TextInput type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="0" invalid={!!fe("quantity_requested")} />
        </Field>
        <div className="field-row">
          <Field label="Expected dispatch" error={fe("expected_dispatch_at")}>
            <TextInput type="datetime-local" value={dispatch} onChange={(e) => setDispatch(e.target.value)} />
          </Field>
          <Field label="Expected arrival" error={fe("expected_arrival_at")}>
            <TextInput type="datetime-local" value={arrival} onChange={(e) => setArrival(e.target.value)} />
          </Field>
        </div>
        <Field label="Notes" error={fe("notes")}>
          <TextArea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason for the transfer, handling instructions…" />
        </Field>
      </div>
    </Modal>
  );
}
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TransfersApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { DeliveryCoordination, DeliveryPayer, DeliveryPhoneStatus, DeliveryStatus } from "@/api/types";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Field, Icon, LoadingState, Modal, SelectInput, TextArea, TextInput, useToast } from "@/components/ui";
import { formatDateTime, formatMoney, humanize, localInputToISO } from "@/lib/formatters";

const PAYERS: DeliveryPayer[] = ["CENTRAL", "SENDER", "RECEIVER", "PARTNER", "UNDECIDED"];
const PHONE_STATUSES: DeliveryPhoneStatus[] = ["PENDING", "CONFIRMED", "CANCELLED"];
const DELIVERY_STATUSES: DeliveryStatus[] = ["NOT_ARRANGED", "ARRANGED_BY_PHONE", "DISPATCHED", "RECEIVED", "FAILED", "DISCREPANCY"];

function DeliveryCallModal({ transferId, onClose }: { transferId: number; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [method, setMethod] = useState("pickup");
  const [provider, setProvider] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [payer, setPayer] = useState<DeliveryPayer>("UNDECIDED");
  const [cost, setCost] = useState("");
  const [currency, setCurrency] = useState("ETB");
  const [pickup, setPickup] = useState("");
  const [arrival, setArrival] = useState("");
  const [phoneStatus, setPhoneStatus] = useState<DeliveryPhoneStatus>("PENDING");
  const [deliveryStatus, setDeliveryStatus] = useState<DeliveryStatus>("NOT_ARRANGED");
  const [notes, setNotes] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () =>
      TransfersApi.addDelivery(transferId, {
        transport_method: method.trim(),
        transport_provider: provider.trim(),
        contact_person_name: contactName.trim(),
        contact_phone: contactPhone.trim(),
        transport_payer: payer,
        estimated_cost: cost.trim() ? cost.trim() : null,
        currency: currency.trim() || "ETB",
        agreed_pickup_at: localInputToISO(pickup) ?? null,
        expected_arrival_at: localInputToISO(arrival) ?? null,
        phone_coordination_status: phoneStatus,
        delivery_status: deliveryStatus,
        notes: notes.trim(),
      }),
    onSuccess: () => {
      toast.success("Call logged", "A new delivery-coordination entry was added to the audit trail.");
      qc.invalidateQueries({ queryKey: ["delivery-coordination", transferId] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not log call", e.detail); }
      else toast.error("Could not log call", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Log coordination call"
      subtitle="Each entry is a new, immutable record of a phone arrangement."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button icon="phone" loading={mutation.isPending} onClick={() => mutation.mutate()}>Log call</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="field-row">
          <Field label="Transport method" error={fe("transport_method")}>
            <TextInput value={method} onChange={(e) => setMethod(e.target.value)} placeholder="pickup, courier, own vehicle…" />
          </Field>
          <Field label="Transport provider" error={fe("transport_provider")}>
            <TextInput value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="Carrier or driver name" />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Contact person" error={fe("contact_person_name")}>
            <TextInput value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="Who you spoke with" />
          </Field>
          <Field label="Contact phone" error={fe("contact_phone")}>
            <TextInput value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="+251…" />
          </Field>
        </div>
        <div className="field-row-3">
          <Field label="Who pays" error={fe("transport_payer")}>
            <SelectInput value={payer} onChange={(e) => setPayer(e.target.value as DeliveryPayer)}>
              {PAYERS.map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
            </SelectInput>
          </Field>
          <Field label="Estimated cost" error={fe("estimated_cost")}>
            <TextInput type="number" min={0} step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" />
          </Field>
          <Field label="Currency" error={fe("currency")}>
            <TextInput value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="ETB" />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Agreed pickup" error={fe("agreed_pickup_at")}>
            <TextInput type="datetime-local" value={pickup} onChange={(e) => setPickup(e.target.value)} />
          </Field>
          <Field label="Expected arrival" error={fe("expected_arrival_at")}>
            <TextInput type="datetime-local" value={arrival} onChange={(e) => setArrival(e.target.value)} />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Phone coordination" error={fe("phone_coordination_status")}>
            <SelectInput value={phoneStatus} onChange={(e) => setPhoneStatus(e.target.value as DeliveryPhoneStatus)}>
              {PHONE_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </SelectInput>
          </Field>
          <Field label="Delivery status" error={fe("delivery_status")}>
            <SelectInput value={deliveryStatus} onChange={(e) => setDeliveryStatus(e.target.value as DeliveryStatus)}>
              {DELIVERY_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </SelectInput>
          </Field>
        </div>
        <Field label="Notes" error={fe("notes")}>
          <TextArea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What was agreed on the call…" />
        </Field>
      </div>
    </Modal>
  );
}

function CallEntry({ call }: { call: DeliveryCoordination }) {
  return (
    <div className="timeline-item">
      <div className="timeline-dot" style={{ background: "var(--blue-050)", color: "var(--blue)" }}>
        <Icon name="phone" size={15} />
      </div>
      <div className="timeline-content">
        <div className="row wrap" style={{ gap: 6, alignItems: "center" }}>
          <span className="t-title">{call.contact_person_name || call.transport_provider || "Coordination call"}</span>
          <Badge value={call.phone_coordination_status} dot={false} />
          <Badge value={call.delivery_status} dot={false} />
        </div>
        <div className="t-meta">
          {formatDateTime(call.created_at)} · {call.coordinator_username || "—"}
          {call.contact_phone && <> · <span className="mono">{call.contact_phone}</span></>}
        </div>
        <div className="t-body">
          <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
            {call.transport_method && <span className="chip">{humanize(call.transport_method)}</span>}
            {call.transport_provider && <span className="chip">{call.transport_provider}</span>}
            <span className="chip">Payer: {humanize(call.transport_payer)}</span>
            {call.estimated_cost && <span className="chip">{formatMoney(call.estimated_cost, call.currency)}</span>}
          </div>
          {(call.agreed_pickup_at || call.expected_arrival_at) && (
            <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
              {call.agreed_pickup_at && <>Pickup {formatDateTime(call.agreed_pickup_at)}</>}
              {call.agreed_pickup_at && call.expected_arrival_at && " · "}
              {call.expected_arrival_at && <>Arrival {formatDateTime(call.expected_arrival_at)}</>}
            </div>
          )}
          {call.notes && <div style={{ marginTop: 6 }}>{call.notes}</div>}
        </div>
      </div>
    </div>
  );
}

export function DeliveryCoordinationPanel({
  transferId,
  canAdd,
}: {
  transferId: number;
  canAdd: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const q = useQuery({
    queryKey: ["delivery-coordination", transferId],
    queryFn: () => TransfersApi.deliveryLog(transferId),
  });

  return (
    <Card>
      <CardHeader
        title="Delivery coordination"
        subtitle="Phone-arranged transport · audit trail of calls"
        icon="phone"
        action={canAdd && <Button size="sm" icon="plus" onClick={() => setAdding(true)}>Log call</Button>}
      />
      <CardBody>
        {q.isLoading ? (
          <LoadingState label="Loading call log…" />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data || q.data.results.length === 0 ? (
          <EmptyState
            icon="phone"
            title="No calls logged yet"
            message={canAdd ? "Record each phone arrangement so the delivery history stays auditable." : "Delivery calls arranged for this transfer will appear here."}
            action={canAdd ? <Button icon="plus" onClick={() => setAdding(true)}>Log first call</Button> : undefined}
          />
        ) : (
          <div className="timeline">
            {q.data.results.map((call) => <CallEntry key={call.id} call={call} />)}
          </div>
        )}
      </CardBody>
      {adding && <DeliveryCallModal transferId={transferId} onClose={() => setAdding(false)} />}
    </Card>
  );
}
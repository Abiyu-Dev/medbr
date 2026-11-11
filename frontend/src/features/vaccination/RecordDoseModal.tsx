import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { VaccinationApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { VaccinationRecord, VaccineFollowUp } from "@/api/types";
import { Button, Field, Icon, Modal, TextArea, TextInput, useToast } from "@/components/ui";
import { BatchSelect, PatientSelect, ProductSelect } from "@/components/forms/Pickers";
import { formatDate, localInputToISO, nowLocalInput } from "@/lib/formatters";

export function RecordDoseModal({
  presetPatient,
  onClose,
}: {
  presetPatient?: number | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [patient, setPatient] = useState<number | null>(presetPatient ?? null);
  const [product, setProduct] = useState<number | "">("");
  const [dose, setDose] = useState("1");
  const [administered, setAdministered] = useState(nowLocalInput());
  const [batch, setBatch] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<{ record: VaccinationRecord; next_follow_up: VaccineFollowUp | null } | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      VaccinationApi.createRecord({
        patient,
        vaccine_product: product,
        dose_number: Number(dose),
        administered_at: localInputToISO(administered),
        batch,
        notes: notes.trim(),
      }),
    onSuccess: (data) => {
      setResult(data);
      toast.success("Dose recorded", `${data.record.vaccine_product_name} dose ${data.record.dose_number} · ${data.record.patient_name}`);
      qc.invalidateQueries({ queryKey: ["vaccination-records"] });
      qc.invalidateQueries({ queryKey: ["followups"] });
      qc.invalidateQueries({ queryKey: ["due-followups"] });
      qc.invalidateQueries({ queryKey: ["overdue-followups"] });
      qc.invalidateQueries({ queryKey: ["patients"] });
      qc.invalidateQueries({ queryKey: ["patient"] });
      qc.invalidateQueries({ queryKey: ["batches"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not record dose", e.detail); }
      else toast.error("Could not record dose", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const doseNum = Number(dose);
  const valid = patient !== null && product !== "" && batch !== "" && Number.isInteger(doseNum) && doseNum >= 1 && administered !== "";

  if (result) {
    const { record, next_follow_up } = result;
    return (
      <Modal
        open
        onClose={onClose}
        title="Dose recorded"
        footer={<Button onClick={onClose}>Done</Button>}
      >
        <div className="stack" style={{ gap: 16 }}>
          <div className="alert alert-success" style={{ alignItems: "center" }}>
            <Icon name="check-circle" size={22} />
            <div>
              <strong>{record.vaccine_product_name} · dose {record.dose_number}</strong>
              <div style={{ fontSize: 13, marginTop: 2 }}>{record.patient_name} ({record.patient_number}) · batch {record.batch_number}</div>
            </div>
          </div>
          <div className="detail-grid">
            <div className="detail-item"><div className="dt">Administered</div><div className="dd">{formatDate(record.administered_at)}</div></div>
            <div className="detail-item"><div className="dt">Facility</div><div className="dd">{record.facility_name}</div></div>
            <div className="detail-item"><div className="dt">Recorded by</div><div className="dd">{record.recorded_by_username}</div></div>
          </div>
          {next_follow_up ? (
            <div className="alert alert-info" style={{ alignItems: "center" }}>
              <Icon name="calendar" size={20} />
              <div>
                <strong>Next follow-up scheduled</strong>
                <div style={{ fontSize: 13, marginTop: 2 }}>{next_follow_up.vaccine_product_name} dose {next_follow_up.dose_number} due <strong>{formatDate(next_follow_up.due_date)}</strong>. It now appears in the follow-up queue.</div>
              </div>
            </div>
          ) : (
            <div className="alert alert-info"><Icon name="info" size={16} /><span>No further dose is scheduled for this series — either it is complete or no schedule exists for the next dose.</span></div>
          )}
          <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>Recording a dose consumed one unit from the batch and logged a vaccination-administration stock movement.</p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Record a vaccination dose"
      subtitle="Consumes one unit from the batch and schedules the next dose automatically."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button icon="syringe" loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Record dose</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <Field label="Patient" required error={fe("patient")}>
          <PatientSelect value={patient} onChange={setPatient} invalid={!!fe("patient")} />
        </Field>
        <div className="field-row">
          <Field label="Vaccine" required error={fe("vaccine_product")}>
            <ProductSelect value={product} onChange={(v) => { setProduct(v); setBatch(""); }} category="VACCINE" placeholder="Select vaccine…" invalid={!!fe("vaccine_product")} />
          </Field>
          <Field label="Dose number" required error={fe("dose_number")} help="Position in the series (1, 2, 3…)">
            <TextInput type="number" min={1} step={1} value={dose} onChange={(e) => setDose(e.target.value)} invalid={!!fe("dose_number")} />
          </Field>
        </div>
        <Field label="Batch" required error={fe("batch")} help="Usable vaccine batches at this facility with free stock.">
          <BatchSelect value={batch} onChange={setBatch} productId={product} usableOnly invalid={!!fe("batch")} />
        </Field>
        <Field label="Administered at" required error={fe("administered_at")}>
          <TextInput type="datetime-local" value={administered} onChange={(e) => setAdministered(e.target.value)} invalid={!!fe("administered_at")} />
        </Field>
        <Field label="Notes" error={fe("notes")}>
          <TextArea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Site, reaction, observations…" />
        </Field>
      </div>
    </Modal>
  );
}
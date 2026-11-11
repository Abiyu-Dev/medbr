import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PatientsApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Patient, Sex } from "@/api/types";
import { Button, Checkbox, Field, Icon, Modal, SelectInput, TextInput, useToast } from "@/components/ui";
import { todayISO } from "@/lib/formatters";

const SEXES: Sex[] = ["MALE", "FEMALE", "OTHER", "UNKNOWN"];
const sexLabel = (s: Sex) => s.charAt(0) + s.slice(1).toLowerCase();

export function PatientFormModal({
  patient,
  onClose,
  onSaved,
}: {
  patient?: Patient | null;
  onClose: () => void;
  onSaved?: (p: Patient) => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const editing = !!patient;
  const [fullName, setFullName] = useState(patient?.full_name ?? "");
  const [number, setNumber] = useState(patient?.patient_number ?? "");
  const [dob, setDob] = useState(patient?.date_of_birth ?? "");
  const [sex, setSex] = useState<Sex>(patient?.sex ?? "UNKNOWN");
  const [guardianName, setGuardianName] = useState(patient?.guardian_name ?? "");
  const [guardianPhone, setGuardianPhone] = useState(patient?.guardian_phone ?? "");
  const [patientPhone, setPatientPhone] = useState(patient?.patient_phone ?? "");
  const [area, setArea] = useState(patient?.address_area ?? "");
  const [consent, setConsent] = useState(patient?.consent_given ?? false);
  const [consentDate, setConsentDate] = useState(patient?.consent_date ?? "");
  const [active, setActive] = useState(patient?.active ?? true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () => {
      if (editing) {
        return PatientsApi.update(patient!.id, {
          full_name: fullName.trim(),
          guardian_name: guardianName.trim(),
          guardian_phone: guardianPhone.trim(),
          patient_phone: patientPhone.trim(),
          address_area: area.trim(),
          consent_given: consent,
          consent_date: consentDate || null,
          active,
        });
      }
      const body: Record<string, unknown> = {
        full_name: fullName.trim(),
        date_of_birth: dob,
        sex,
        guardian_name: guardianName.trim(),
        guardian_phone: guardianPhone.trim(),
        patient_phone: patientPhone.trim(),
        address_area: area.trim(),
        consent_given: consent,
        consent_date: consentDate || null,
      };
      if (number.trim()) body.patient_number = number.trim();
      return PatientsApi.create(body);
    },
    onSuccess: (data) => {
      toast.success(editing ? "Patient updated" : "Patient registered", data.full_name);
      qc.invalidateQueries({ queryKey: ["patients"] });
      qc.invalidateQueries({ queryKey: ["patient", data.id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onSaved?.(data);
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not save patient", e.detail); }
      else toast.error("Could not save patient", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid = fullName.trim() !== "" && (editing || dob !== "");

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={editing ? "Edit patient" : "Register patient"}
      subtitle="Vaccination register — identifiable details stay within this facility."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{editing ? "Save changes" : "Register patient"}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <Field label="Full name" required error={fe("full_name")}>
          <TextInput value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Patient full name" invalid={!!fe("full_name")} />
        </Field>
        <div className="field-row-3">
          <Field label="Patient number" error={fe("patient_number")} help={editing ? "Immutable" : "Auto-generated if blank"}>
            <TextInput value={number} onChange={(e) => setNumber(e.target.value)} placeholder="P-001-000001" disabled={editing} />
          </Field>
          <Field label="Date of birth" required={!editing} error={fe("date_of_birth")} help={editing ? "Immutable" : undefined}>
            <TextInput type="date" max={todayISO()} value={dob} onChange={(e) => setDob(e.target.value)} disabled={editing} invalid={!!fe("date_of_birth")} />
          </Field>
          <Field label="Sex" error={fe("sex")} help={editing ? "Immutable" : undefined}>
            <SelectInput value={sex} onChange={(e) => setSex(e.target.value as Sex)} disabled={editing}>
              {SEXES.map((s) => <option key={s} value={s}>{sexLabel(s)}</option>)}
            </SelectInput>
          </Field>
        </div>
        <div className="field-row">
          <Field label="Guardian name" error={fe("guardian_name")}>
            <TextInput value={guardianName} onChange={(e) => setGuardianName(e.target.value)} placeholder="Parent / guardian" />
          </Field>
          <Field label="Guardian phone" error={fe("guardian_phone")}>
            <TextInput value={guardianPhone} onChange={(e) => setGuardianPhone(e.target.value)} placeholder="+251…" />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Patient phone" error={fe("patient_phone")}>
            <TextInput value={patientPhone} onChange={(e) => setPatientPhone(e.target.value)} placeholder="+251…" />
          </Field>
          <Field label="Address / area" error={fe("address_area")}>
            <TextInput value={area} onChange={(e) => setArea(e.target.value)} placeholder="Kebele, town…" />
          </Field>
        </div>
        <div className="divider" style={{ margin: "4px 0" }} />
        <Checkbox label="Consent given for vaccination services" checked={consent} onChange={(e) => { setConsent(e.target.checked); if (e.target.checked && !consentDate) setConsentDate(todayISO()); }} />
        {consent && (
          <Field label="Consent date" error={fe("consent_date")}>
            <TextInput type="date" max={todayISO()} value={consentDate} onChange={(e) => setConsentDate(e.target.value)} />
          </Field>
        )}
        {editing && (
          <>
            <div className="alert alert-info"><Icon name="info" size={16} /><span>Deactivating a patient hides them from active registers but keeps their vaccination history.</span></div>
            <Checkbox label="Patient is active" checked={active} onChange={(e) => setActive(e.target.checked)} />
          </>
        )}
      </div>
    </Modal>
  );
}
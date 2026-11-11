import { useState, type FormEvent } from "react";
import { FacilitiesApi } from "@/api/endpoints";
import type { Facility, FacilityType } from "@/api/types";
import {
  Button,
  Field,
  TextInput,
  SelectInput,
  TextArea,
  Checkbox,
  Icon,
} from "@/components/ui";
import { LocationPicker } from "@/components/map/Maps";
import { isApiError } from "@/api/client";

const FACILITY_TYPES: { value: FacilityType; label: string }[] = [
  { value: "CLINIC", label: "Clinic" },
  { value: "HOSPITAL", label: "Hospital" },
  { value: "HEALTH_CENTER", label: "Health Center" },
  { value: "PHARMACY", label: "Pharmacy" },
  { value: "OTHER", label: "Other" },
];

interface FormState {
  name: string;
  facility_type: FacilityType;
  registration_number: string;
  region: string;
  zone: string;
  woreda: string;
  kebele: string;
  town: string;
  address: string;
  landmark: string;
  latitude: string;
  longitude: string;
  contact_phone: string;
  contact_email: string;
  storage_capacity_notes: string;
  has_cold_chain: boolean;
  cold_chain_notes: string;
  provides_vaccination_services: boolean;
}

const INITIAL: FormState = {
  name: "",
  facility_type: "HEALTH_CENTER",
  registration_number: "",
  region: "",
  zone: "",
  woreda: "",
  kebele: "",
  town: "",
  address: "",
  landmark: "",
  latitude: "",
  longitude: "",
  contact_phone: "",
  contact_email: "",
  storage_capacity_notes: "",
  has_cold_chain: false,
  cold_chain_notes: "",
  provides_vaccination_services: false,
};

export function ApplyForm({ onSubmitted }: { onSubmitted: (f: Facility) => void }) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [detail, setDetail] = useState("");
  const [loading, setLoading] = useState(false);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setDetail("");
    const local: Record<string, string[]> = {};
    if (!form.name.trim()) local.name = ["Facility name is required."];
    if (!form.region.trim()) local.region = ["Region is required."];
    if (form.latitude && (parseFloat(form.latitude) < -90 || parseFloat(form.latitude) > 90))
      local.latitude = ["Latitude must be between -90 and 90."];
    if (form.longitude && (parseFloat(form.longitude) < -180 || parseFloat(form.longitude) > 180))
      local.longitude = ["Longitude must be between -180 and 180."];
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }
    setLoading(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      for (const key of ["registration_number", "latitude", "longitude"] as const) {
        if (!String(payload[key] ?? "").trim()) delete payload[key];
      }
      const facility = await FacilitiesApi.apply(payload);
      onSubmitted(facility);
    } catch (err) {
      if (isApiError(err) && err.fieldErrors) setErrors(err.fieldErrors);
      else if (isApiError(err)) setDetail(err.detail);
      else setDetail("Could not submit the application.");
    } finally {
      setLoading(false);
    }
  }

  const err = (k: string) => errors[k];

  return (
    <form onSubmit={onSubmit}>
      {detail && (
        <div className="alert alert-danger">
          <Icon name="alert" size={17} />
          <span>{detail}</span>
        </div>
      )}

      <div className="form-section-title" style={{ marginTop: 0 }}>Facility identity</div>
      <Field label="Facility name" required error={err("name")} htmlFor="name">
        <TextInput id="name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Bole Health Center" invalid={!!err("name")} />
      </Field>
      <div className="field-row">
        <Field label="Facility type" required error={err("facility_type")}>
          <SelectInput value={form.facility_type} onChange={(e) => set("facility_type", e.target.value as FacilityType)}>
            {FACILITY_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </SelectInput>
        </Field>
        <Field label="Registration number" error={err("registration_number")} help="Optional, if available">
          <TextInput value={form.registration_number} onChange={(e) => set("registration_number", e.target.value)} />
        </Field>
      </div>

      <div className="form-section-title">Location</div>
      <div className="field-row">
        <Field label="Region" required error={err("region")}>
          <TextInput value={form.region} onChange={(e) => set("region", e.target.value)} placeholder="e.g. Addis Ababa" invalid={!!err("region")} />
        </Field>
        <Field label="Town / City" error={err("town")}>
          <TextInput value={form.town} onChange={(e) => set("town", e.target.value)} />
        </Field>
      </div>
      <div className="field-row-3">
        <Field label="Zone" error={err("zone")}><TextInput value={form.zone} onChange={(e) => set("zone", e.target.value)} /></Field>
        <Field label="Woreda" error={err("woreda")}><TextInput value={form.woreda} onChange={(e) => set("woreda", e.target.value)} /></Field>
        <Field label="Kebele" error={err("kebele")}><TextInput value={form.kebele} onChange={(e) => set("kebele", e.target.value)} /></Field>
      </div>
      <Field label="Address" error={err("address")}><TextInput value={form.address} onChange={(e) => set("address", e.target.value)} /></Field>
      <Field label="Landmark" error={err("landmark")}><TextInput value={form.landmark} onChange={(e) => set("landmark", e.target.value)} placeholder="Nearby landmark to help drivers" /></Field>
      <div className="field-row">
        <Field label="Latitude" error={err("latitude")} help="-90 to 90">
          <TextInput value={form.latitude} onChange={(e) => set("latitude", e.target.value)} placeholder="9.010000" invalid={!!err("latitude")} />
        </Field>
        <Field label="Longitude" error={err("longitude")} help="-180 to 180">
          <TextInput value={form.longitude} onChange={(e) => set("longitude", e.target.value)} placeholder="38.760000" invalid={!!err("longitude")} />
        </Field>
      </div>
      <Field label="Map pin" help="Click the map to drop a pin, or drag the marker. Coordinates fill in automatically.">
        <LocationPicker
          latitude={form.latitude}
          longitude={form.longitude}
          onChange={(lat, lng) => setForm((p) => ({ ...p, latitude: lat, longitude: lng }))}
        />
      </Field>

      <div className="form-section-title">Contact &amp; storage</div>
      <div className="field-row">
        <Field label="Contact phone" error={err("contact_phone")}><TextInput value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} placeholder="+251…" /></Field>
        <Field label="Contact email" error={err("contact_email")}><TextInput type="email" value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field>
      </div>
      <Field label="Storage capacity notes" error={err("storage_capacity_notes")}>
        <TextArea value={form.storage_capacity_notes} onChange={(e) => set("storage_capacity_notes", e.target.value)} placeholder="Shelf space, refrigerator capacity, etc." />
      </Field>
      <div className="field" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Checkbox label="This facility has cold-chain storage" checked={form.has_cold_chain} onChange={(e) => set("has_cold_chain", e.target.checked)} />
        <Checkbox label="This facility provides vaccination services" checked={form.provides_vaccination_services} onChange={(e) => set("provides_vaccination_services", e.target.checked)} />
      </div>
      {form.has_cold_chain && (
        <Field label="Cold-chain notes" error={err("cold_chain_notes")}>
          <TextArea value={form.cold_chain_notes} onChange={(e) => set("cold_chain_notes", e.target.value)} placeholder="Equipment, temperature monitoring, backup power…" />
        </Field>
      )}

      <div className="form-actions">
        <Button type="submit" size="lg" loading={loading} icon="send">Submit application</Button>
      </div>
    </form>
  );
}
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Facility } from "@/api/types";
import { Button, Checkbox, Field, Modal, TextArea, TextInput, useToast } from "@/components/ui";
import { LocationPicker } from "@/components/map/Maps";

export function FacilityEditModal({ facility, onClose }: { facility: Facility; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState(facility.name);
  const [address, setAddress] = useState(facility.address);
  const [landmark, setLandmark] = useState(facility.landmark);
  const [latitude, setLatitude] = useState(facility.latitude ?? "");
  const [longitude, setLongitude] = useState(facility.longitude ?? "");
  const [phone, setPhone] = useState(facility.contact_phone);
  const [email, setEmail] = useState(facility.contact_email);
  const [storage, setStorage] = useState(facility.storage_capacity_notes);
  const [coldChain, setColdChain] = useState(facility.has_cold_chain);
  const [coldNotes, setColdNotes] = useState(facility.cold_chain_notes);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () =>
      FacilitiesApi.update(facility.id, {
        name: name.trim(),
        address: address.trim(),
        landmark: landmark.trim(),
        latitude: latitude || null,
        longitude: longitude || null,
        contact_phone: phone.trim(),
        contact_email: email.trim(),
        storage_capacity_notes: storage.trim(),
        has_cold_chain: coldChain,
        cold_chain_notes: coldNotes.trim(),
      }),
    onSuccess: () => {
      toast.success("Facility updated", "Operational profile saved.");
      qc.invalidateQueries({ queryKey: ["facility"] });
      qc.invalidateQueries({ queryKey: ["facilities"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["me"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not save", e.detail); }
      else toast.error("Could not save", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Edit facility profile"
      subtitle="Operational details. Facility type and approval status are managed centrally."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button loading={mutation.isPending} disabled={name.trim() === ""} onClick={() => mutation.mutate()}>Save changes</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <Field label="Facility name" required error={fe("name")}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} invalid={!!fe("name")} />
        </Field>
        <div className="field-row">
          <Field label="Contact phone" error={fe("contact_phone")}>
            <TextInput value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+251…" />
          </Field>
          <Field label="Contact email" error={fe("contact_email")}>
            <TextInput type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        </div>
        <Field label="Address" error={fe("address")}>
          <TextInput value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field label="Landmark" error={fe("landmark")}>
          <TextInput value={landmark} onChange={(e) => setLandmark(e.target.value)} placeholder="Helps drivers find the facility" />
        </Field>
        <div className="field-row">
          <Field label="Latitude" error={fe("latitude")}>
            <TextInput value={latitude} onChange={(e) => setLatitude(e.target.value)} placeholder="9.010000" />
          </Field>
          <Field label="Longitude" error={fe("longitude")}>
            <TextInput value={longitude} onChange={(e) => setLongitude(e.target.value)} placeholder="38.760000" />
          </Field>
        </div>
        <Field label="Map pin" help="Click the map to drop a pin, or drag the marker.">
          <LocationPicker latitude={latitude} longitude={longitude} onChange={(lat, lng) => { setLatitude(lat); setLongitude(lng); }} />
        </Field>
        <Field label="Storage capacity notes" error={fe("storage_capacity_notes")}>
          <TextArea rows={2} value={storage} onChange={(e) => setStorage(e.target.value)} />
        </Field>
        <Checkbox label="This facility has cold-chain storage" checked={coldChain} onChange={(e) => setColdChain(e.target.checked)} />
        {coldChain && (
          <Field label="Cold-chain notes" error={fe("cold_chain_notes")}>
            <TextArea rows={2} value={coldNotes} onChange={(e) => setColdNotes(e.target.value)} />
          </Field>
        )}
      </div>
    </Modal>
  );
}
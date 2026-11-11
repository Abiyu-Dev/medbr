import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BatchesApi, FacilitiesApi, PatientsApi, ProductsApi } from "@/api/endpoints";
import type { Patient, ProductCategory } from "@/api/types";
import { SelectInput, TextInput, Icon } from "@/components/ui";
import { useDebounce } from "@/hooks/useDebounce";
import { ageFromDob } from "@/lib/formatters";

type IdValue = number | "";

export function FacilitySelect({
  value,
  onChange,
  placeholder = "Select facility…",
  onlyApproved = true,
  excludeId,
  disabled,
  invalid,
  network = false,
}: {
  value: IdValue;
  onChange: (v: IdValue) => void;
  placeholder?: string;
  onlyApproved?: boolean;
  excludeId?: number | null;
  disabled?: boolean;
  invalid?: boolean;
  /** Use the approved-network directory (`/facilities/map/`) instead of the scoped list. */
  network?: boolean;
}) {
  const q = useQuery({
    queryKey: ["facilities", network ? "network" : "picker"],
    queryFn: async () => {
      if (network) {
        const points = await FacilitiesApi.map();
        return points.map((p) => ({ id: p.id, name: p.name, region: p.region, status: "APPROVED" }));
      }
      return (await FacilitiesApi.list({ ordering: "name" })).results;
    },
    staleTime: 120_000,
  });
  const facilities = (q.data ?? [])
    .filter((f) => !onlyApproved || f.status === "APPROVED")
    .filter((f) => f.id !== excludeId);
  return (
    <SelectInput
      value={value === "" ? "" : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
      disabled={disabled || q.isLoading}
      invalid={invalid}
    >
      <option value="">{q.isLoading ? "Loading facilities…" : placeholder}</option>
      {facilities.map((f) => (
        <option key={f.id} value={f.id}>
          {f.name} · {f.region}
        </option>
      ))}
    </SelectInput>
  );
}

export function ProductSelect({
  value,
  onChange,
  category,
  placeholder = "Select product…",
  disabled,
  invalid,
}: {
  value: IdValue;
  onChange: (v: IdValue) => void;
  category?: ProductCategory;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const q = useQuery({
    queryKey: ["products", "picker", category ?? "all"],
    queryFn: () => ProductsApi.list({ ordering: "name", category }),
    staleTime: 120_000,
  });
  const products = (q.data?.results ?? []).filter((p) => p.active);
  return (
    <SelectInput
      value={value === "" ? "" : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
      disabled={disabled || q.isLoading}
      invalid={invalid}
    >
      <option value="">{q.isLoading ? "Loading products…" : placeholder}</option>
      {products.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name} {p.strength ? `· ${p.strength}` : ""} ({p.unit_of_measure})
        </option>
      ))}
    </SelectInput>
  );
}

export function BatchSelect({
  value,
  onChange,
  productId,
  facilityId,
  central = false,
  usableOnly = true,
  placeholder = "Select batch…",
  disabled,
  invalid,
}: {
  value: IdValue;
  onChange: (v: IdValue) => void;
  productId?: number | "";
  facilityId?: number | "";
  central?: boolean;
  usableOnly?: boolean;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const params: Record<string, string | number | undefined> = { ordering: "expiry_date" };
  if (productId) params.product = productId;
  // Facility users must not send ?facility= (server infers own facility).
  if (central && facilityId) params.facility = facilityId;
  const enabled = !central || !!facilityId;
  const q = useQuery({
    queryKey: ["batches", "picker", params],
    queryFn: () => BatchesApi.list(params),
    enabled,
    staleTime: 30_000,
  });
  const batches = (q.data?.results ?? []).filter(
    (b) => !usableOnly || (b.quantity_available > 0 && b.storage_status === "OK" && !b.is_expired),
  );
  return (
    <SelectInput
      value={value === "" ? "" : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
      disabled={disabled || q.isLoading || !enabled}
      invalid={invalid}
    >
      <option value="">
        {!enabled ? "Select a facility first…" : q.isLoading ? "Loading batches…" : placeholder}
      </option>
      {batches.map((b) => (
        <option key={b.id} value={b.id}>
          {b.batch_number} · {b.product_name} · {b.quantity_available} avail · exp {b.expiry_date}
        </option>
      ))}
    </SelectInput>
  );
}

export function PatientSelect({
  value,
  onChange,
  disabled,
  invalid,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 300);
  const list = useQuery({
    queryKey: ["patients", "picker", debounced],
    queryFn: () => PatientsApi.list({ search: debounced || undefined }),
    enabled: open,
    staleTime: 30_000,
  });
  const selected = useQuery({
    queryKey: ["patient", value],
    queryFn: () => PatientsApi.get(value as number),
    enabled: !!value,
    staleTime: 60_000,
  });
  const picked: Patient | undefined = selected.data;

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className={`input ${invalid ? "invalid" : ""}`}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          textAlign: "left",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        <span className="truncate">
          {picked ? `${picked.full_name} · ${picked.patient_number}` : "Select patient…"}
        </span>
        <Icon name="chevron-down" size={15} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 40,
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            boxShadow: "0 12px 32px rgba(20,40,38,.16)",
            padding: 8,
          }}
        >
          <TextInput
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or patient number…"
          />
          <div style={{ maxHeight: 220, overflowY: "auto", marginTop: 6 }}>
            {list.isLoading ? (
              <div className="muted" style={{ padding: 10, fontSize: 13 }}>Searching…</div>
            ) : (list.data?.results.length ?? 0) === 0 ? (
              <div className="muted" style={{ padding: 10, fontSize: 13 }}>No patients found.</div>
            ) : (
              list.data!.results.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="dropdown-item"
                  onClick={() => {
                    onChange(p.id);
                    setOpen(false);
                    setSearch("");
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className="cell-title truncate" style={{ display: "block" }}>{p.full_name}</span>
                    <span className="cell-sub" style={{ display: "block" }}>
                      {p.patient_number} · {ageFromDob(p.date_of_birth)} · {p.sex_display || p.sex}
                    </span>
                  </span>
                  {value === p.id && <Icon name="check" size={16} />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
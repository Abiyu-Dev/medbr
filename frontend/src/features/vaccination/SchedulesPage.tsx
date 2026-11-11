import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { SchedulesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { VaccineSchedule } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canManageSchedules } from "@/lib/permissions";
import { Badge, Button, Card, Checkbox, DataTable, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, TextInput, useToast, type Column } from "@/components/ui";
import { ProductSelect } from "@/components/forms/Pickers";
import { formatDate, todayISO } from "@/lib/formatters";

function ScheduleFormModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [product, setProduct] = useState<number | "">("");
  const [dose, setDose] = useState("1");
  const [ageDays, setAgeDays] = useState("");
  const [ageLabel, setAgeLabel] = useState("");
  const [interval, setInterval] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(todayISO());
  const [sourceName, setSourceName] = useState("");
  const [sourceVersion, setSourceVersion] = useState("");
  const [active, setActive] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () =>
      SchedulesApi.create({
        vaccine_product: product,
        dose_number: Number(dose),
        recommended_age_days: ageDays.trim() === "" ? null : Number(ageDays),
        recommended_age_label: ageLabel.trim(),
        minimum_interval_days: interval.trim() === "" ? null : Number(interval),
        effective_from: effectiveFrom,
        source_name: sourceName.trim(),
        source_version: sourceVersion.trim(),
        active,
      }),
    onSuccess: (data) => {
      toast.success("Schedule version created", `${data.vaccine_product_name} dose ${data.dose_number}`);
      qc.invalidateQueries({ queryKey: ["schedules"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not create schedule", e.detail); }
      else toast.error("Could not create schedule", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const doseNum = Number(dose);
  const hasRule = ageDays.trim() !== "" || interval.trim() !== "";
  const valid =
    product !== "" && Number.isInteger(doseNum) && doseNum >= 1 && effectiveFrom !== "" &&
    sourceName.trim() !== "" && hasRule;

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="New schedule version"
      subtitle="Versioned dose rules from an approved source."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button icon="calendar" loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Create version</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="alert alert-info"><Icon name="info" size={16} /><span>Creating an <strong>active</strong> version for a vaccine + dose supersedes the previous active version. Historical records keep their original schedule.</span></div>
        <div className="field-row">
          <Field label="Vaccine" required error={fe("vaccine_product")}>
            <ProductSelect value={product} onChange={setProduct} category="VACCINE" placeholder="Select vaccine…" invalid={!!fe("vaccine_product")} />
          </Field>
          <Field label="Dose number" required error={fe("dose_number")}>
            <TextInput type="number" min={1} step={1} value={dose} onChange={(e) => setDose(e.target.value)} invalid={!!fe("dose_number")} />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Recommended age (days)" error={fe("recommended_age_days")} help="Age at which this dose is given.">
            <TextInput type="number" min={0} step={1} value={ageDays} onChange={(e) => setAgeDays(e.target.value)} placeholder="e.g. 42" invalid={!!fe("recommended_age_days")} />
          </Field>
          <Field label="Age label" error={fe("recommended_age_label")} help="Human-readable, e.g. “6 weeks”.">
            <TextInput value={ageLabel} onChange={(e) => setAgeLabel(e.target.value)} placeholder="6 weeks" />
          </Field>
        </div>
        <Field label="Minimum interval (days)" error={fe("minimum_interval_days")} help="Shortest gap since the previous dose. At least one of age or interval is required so due dates can be computed.">
          <TextInput type="number" min={0} step={1} value={interval} onChange={(e) => setInterval(e.target.value)} placeholder="e.g. 28" invalid={!!fe("minimum_interval_days")} />
        </Field>
        {!hasRule && <div className="alert alert-warning"><Icon name="alert" size={16} /><span>Set a recommended age or a minimum interval (or both).</span></div>}
        <div className="field-row">
          <Field label="Effective from" required error={fe("effective_from")}>
            <TextInput type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} invalid={!!fe("effective_from")} />
          </Field>
          <Field label="Source version" error={fe("source_version")}>
            <TextInput value={sourceVersion} onChange={(e) => setSourceVersion(e.target.value)} placeholder="2024 revision" />
          </Field>
        </div>
        <Field label="Source name" required error={fe("source_name")} help="The approved schedule authority, e.g. “Ethiopia EPI”.">
          <TextInput value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="Ethiopia EPI" invalid={!!fe("source_name")} />
        </Field>
        <Checkbox label="Active (supersedes the previous active version for this dose)" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </div>
    </Modal>
  );
}

export function SchedulesPage() {
  const { user } = useAuth();
  const canManage = canManageSchedules(user?.role);
  const list = useList<VaccineSchedule>(["schedules"], SchedulesApi.list, { vaccine_product: "", dose_number: "", active: "" }, "dose_number");
  const [create, setCreate] = useState(false);

  const columns: Column<VaccineSchedule>[] = [
    { key: "vaccine", header: "Vaccine", render: (s) => <span className="cell-title">{s.vaccine_product_name}</span> },
    { key: "dose", header: "Dose", align: "right", sortField: "dose_number", render: (s) => <Badge tone="teal" dot={false}>#{s.dose_number}</Badge> },
    {
      key: "age", header: "Recommended age",
      render: (s) => s.recommended_age_label ? <span>{s.recommended_age_label}{s.recommended_age_days !== null && <span className="cell-sub"> · {s.recommended_age_days}d</span>}</span>
        : s.recommended_age_days !== null ? <span>{s.recommended_age_days} days</span> : <span className="faint">—</span>,
    },
    { key: "interval", header: "Min interval", align: "right", render: (s) => s.minimum_interval_days !== null ? <span>{s.minimum_interval_days}d</span> : <span className="faint">—</span> },
    { key: "effective", header: "Effective from", sortField: "effective_from", render: (s) => formatDate(s.effective_from) },
    {
      key: "source", header: "Source",
      render: (s) => (
        <div className="stack" style={{ gap: 2 }}>
          <span style={{ fontSize: 13 }}>{s.source_name}</span>
          {s.source_version && <span className="cell-sub">{s.source_version}</span>}
        </div>
      ),
    },
    { key: "active", header: "Status", render: (s) => s.active ? <Badge tone="green" dot={false}>Active</Badge> : <Badge tone="slate" dot={false}>Superseded</Badge> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Vaccination"
        title={canManage ? "Vaccine schedules" : "Schedule reference"}
        description="Versioned dose rules from an approved source. These drive automatic due-date calculation when a dose is recorded."
        actions={canManage && <Button icon="plus" onClick={() => setCreate(true)}>New version</Button>}
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search vaccine or source…" />
          <div style={{ minWidth: 180, flex: "0 1 220px" }}>
            <ProductSelect value={list.filters.vaccine_product ? Number(list.filters.vaccine_product) : ""} onChange={(v) => list.setFilter("vaccine_product", v === "" ? "" : String(v))} category="VACCINE" placeholder="All vaccines" />
          </div>
          <SelectInput value={list.filters.active ?? ""} onChange={(e) => list.setFilter("active", e.target.value)} style={{ width: "auto" }}>
            <option value="">All versions</option>
            <option value="true">Active</option>
            <option value="false">Superseded</option>
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(s) => s.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "calendar", title: "No schedule versions", message: canManage ? "Create a schedule version to enable automatic due-date calculation." : "No schedule rules have been published yet.", action: canManage ? <Button icon="plus" onClick={() => setCreate(true)}>New version</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {create && <ScheduleFormModal onClose={() => setCreate(false)} />}
    </div>
  );
}
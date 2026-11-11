import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PatientsApi } from "@/api/endpoints";
import type { Patient } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canVaccinate } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, PageHeader, SearchBox, SelectInput, type Column } from "@/components/ui";
import { ageFromDob, formatDate } from "@/lib/formatters";
import { PatientFormModal } from "./PatientFormModal";

export function PatientsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const list = useList<Patient>(["patients"], PatientsApi.list, { active: "", sex: "" }, "full_name");
  const [create, setCreate] = useState(false);
  const canCreate = canVaccinate(user?.role) && !!user?.facility;

  useEffect(() => {
    if (params.get("new") === "1") setCreate(true);
    if (params.get("new")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<Patient>[] = [
    {
      key: "patient",
      header: "Patient",
      sortField: "full_name",
      render: (p) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{p.full_name}</span>
          <span className="cell-sub mono">{p.patient_number}</span>
        </div>
      ),
    },
    { key: "age", header: "Age / Sex", render: (p) => <span>{ageFromDob(p.date_of_birth)} · {p.sex_display || p.sex}</span> },
    {
      key: "contact",
      header: "Contact",
      render: (p) => (
        <div className="stack" style={{ gap: 2 }}>
          <span style={{ fontSize: 13 }}>{p.guardian_name || p.patient_phone || "—"}</span>
          {p.guardian_phone && <span className="cell-sub mono">{p.guardian_phone}</span>}
        </div>
      ),
    },
    { key: "consent", header: "Consent", render: (p) => p.consent_given ? <Badge tone="green" dot={false}>Given</Badge> : <Badge tone="amber" dot={false}>Pending</Badge> },
    { key: "active", header: "Status", render: (p) => p.active ? <Badge tone="teal" dot={false}>Active</Badge> : <Badge tone="slate" dot={false}>Inactive</Badge> },
    { key: "registered", header: "Registered", sortField: "created_at", render: (p) => formatDate(p.created_at) },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Vaccination"
        title="Patients"
        description="The facility vaccination register. Patient details are scoped to this facility and never appear in network aggregates."
        actions={canCreate && <Button icon="plus" onClick={() => setCreate(true)}>Register patient</Button>}
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search name, number or phone…" />
          <SelectInput value={list.filters.active ?? ""} onChange={(e) => list.setFilter("active", e.target.value)} style={{ width: "auto" }}>
            <option value="">All patients</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </SelectInput>
          <SelectInput value={list.filters.sex ?? ""} onChange={(e) => list.setFilter("sex", e.target.value)} style={{ width: "auto" }}>
            <option value="">All sexes</option>
            <option value="MALE">Male</option>
            <option value="FEMALE">Female</option>
            <option value="OTHER">Other</option>
            <option value="UNKNOWN">Unknown</option>
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(p) => p.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(p) => navigate(`/patients/${p.id}`)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "user", title: "No patients yet", message: "Register a patient to begin recording vaccinations and follow-ups.", action: canCreate ? <Button icon="plus" onClick={() => setCreate(true)}>Register patient</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {create && <PatientFormModal onClose={() => setCreate(false)} onSaved={(p) => navigate(`/patients/${p.id}`)} />}
    </div>
  );
}
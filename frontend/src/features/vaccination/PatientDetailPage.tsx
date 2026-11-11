import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PatientsApi, VaccinationApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { canVaccinate } from "@/lib/permissions";
import { Badge, Button, Card, CardBody, CardHeader, DataTable, EmptyState, ErrorState, Icon, LoadingState, PageHeader, type Column } from "@/components/ui";
import type { VaccinationRecord } from "@/api/types";
import { ageFromDob, formatDate, formatDateTime } from "@/lib/formatters";
import { PatientFormModal } from "./PatientFormModal";
import { RecordDoseModal } from "./RecordDoseModal";

export function PatientDetailPage() {
  const { id } = useParams();
  const patientId = Number(id);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [edit, setEdit] = useState(false);
  const [recordDose, setRecordDose] = useState(false);
  const canEdit = canVaccinate(user?.role);
  const canRecord = canVaccinate(user?.role) && !!user?.facility;

  const q = useQuery({
    queryKey: ["patient", patientId],
    queryFn: () => PatientsApi.get(patientId),
    enabled: Number.isFinite(patientId),
  });
  const records = useQuery({
    queryKey: ["vaccination-records", "patient", patientId],
    queryFn: () => VaccinationApi.records({ patient: patientId, ordering: "-administered_at" }),
    enabled: Number.isFinite(patientId),
  });
  const followups = useQuery({
    queryKey: ["followups", "patient", patientId],
    queryFn: () => VaccinationApi.followups({ patient: patientId, ordering: "due_date" }),
    enabled: Number.isFinite(patientId),
  });

  if (q.isLoading) return <LoadingState label="Loading patient…" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;

  const columns: Column<VaccinationRecord>[] = [
    { key: "vaccine", header: "Vaccine", render: (r) => <span className="cell-title">{r.vaccine_product_name}</span> },
    { key: "dose", header: "Dose", align: "right", render: (r) => <Badge tone="teal" dot={false}>#{r.dose_number}</Badge> },
    { key: "administered", header: "Administered", render: (r) => formatDateTime(r.administered_at) },
    { key: "batch", header: "Batch", render: (r) => <span className="mono" style={{ fontSize: 12.5 }}>{r.batch_number}</span> },
    { key: "by", header: "Recorded by", render: (r) => r.recorded_by_username },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Vaccination · Patient"
        title={p.full_name}
        description={`${p.patient_number} · ${p.facility_name}`}
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            <Button variant="ghost" icon="chevron-left" onClick={() => navigate("/patients")}>All patients</Button>
            {canEdit && <Button variant="secondary" icon="edit" onClick={() => setEdit(true)}>Edit</Button>}
            {canRecord && <Button icon="syringe" onClick={() => setRecordDose(true)}>Record dose</Button>}
          </div>
        }
      />

      <Card>
        <CardHeader title="Patient profile" icon="user" action={p.active ? <Badge tone="teal" dot={false}>Active</Badge> : <Badge tone="slate" dot={false}>Inactive</Badge>} />
        <CardBody>
          <div className="detail-grid">
            <div className="detail-item"><div className="dt">Date of birth</div><div className="dd">{formatDate(p.date_of_birth)} ({ageFromDob(p.date_of_birth)})</div></div>
            <div className="detail-item"><div className="dt">Sex</div><div className="dd">{p.sex_display || p.sex}</div></div>
            <div className="detail-item"><div className="dt">Guardian</div><div className="dd">{p.guardian_name || "—"}</div></div>
            <div className="detail-item"><div className="dt">Guardian phone</div><div className="dd mono">{p.guardian_phone || "—"}</div></div>
            <div className="detail-item"><div className="dt">Patient phone</div><div className="dd mono">{p.patient_phone || "—"}</div></div>
            <div className="detail-item"><div className="dt">Address / area</div><div className="dd">{p.address_area || "—"}</div></div>
            <div className="detail-item"><div className="dt">Consent</div><div className="dd">{p.consent_given ? `Given ${formatDate(p.consent_date)}` : "Not given"}</div></div>
            <div className="detail-item"><div className="dt">Registered</div><div className="dd">{formatDate(p.created_at)}</div></div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Vaccination history" subtitle={`${records.data?.count ?? 0} doses recorded`} icon="syringe" />
        <DataTable
          columns={columns}
          rows={records.data?.results ?? []}
          rowKey={(r) => r.id}
          isLoading={records.isLoading}
          error={records.error}
          onRetry={() => records.refetch()}
          empty={{ icon: "syringe", title: "No doses recorded", message: "Record this patient's first vaccination dose.", action: canRecord ? <Button icon="syringe" onClick={() => setRecordDose(true)}>Record dose</Button> : undefined }}
        />
      </Card>

      <Card>
        <CardHeader
          title="Follow-ups"
          subtitle="Upcoming and past doses in the series"
          icon="calendar"
          action={<Button variant="ghost" size="sm" icon="arrow-right" onClick={() => navigate(`/followups?patient=${p.id}`)}>Manage</Button>}
        />
        <CardBody>
          {followups.isLoading ? (
            <LoadingState label="Loading follow-ups…" />
          ) : followups.error ? (
            <ErrorState error={followups.error} onRetry={() => followups.refetch()} />
          ) : (followups.data?.results.length ?? 0) === 0 ? (
            <EmptyState icon="calendar" title="No follow-ups" message="Follow-ups are created automatically when a dose with a next-in-series is recorded." />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {followups.data!.results.map((f) => (
                <div key={f.id} className="row-between wrap" style={{ gap: 10, padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--r-md)", border: "1px solid var(--border)" }}>
                  <div className="row" style={{ gap: 10 }}>
                    <Icon name="syringe" size={17} />
                    <div className="stack" style={{ gap: 2 }}>
                      <span style={{ fontWeight: 600, fontSize: 13.5 }}>{f.vaccine_product_name} · dose {f.dose_number}</span>
                      <span className="cell-sub">Due {formatDate(f.due_date)}</span>
                    </div>
                  </div>
                  <Badge value={f.effective_status}>{f.status_display}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {edit && <PatientFormModal patient={p} onClose={() => setEdit(false)} />}
      {recordDose && <RecordDoseModal presetPatient={p.id} onClose={() => setRecordDose(false)} />}
    </div>
  );
}
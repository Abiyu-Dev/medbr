import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { VaccinationApi } from "@/api/endpoints";
import type { VaccinationRecord } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canVaccinate } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, PageHeader, SearchBox, type Column } from "@/components/ui";
import { ProductSelect } from "@/components/forms/Pickers";
import { formatDateTime } from "@/lib/formatters";
import { RecordDoseModal } from "./RecordDoseModal";

export function VaccinationRecordsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initialPatient = params.get("patient") ?? "";
  const list = useList<VaccinationRecord>(["vaccination-records"], VaccinationApi.records, { patient: initialPatient, vaccine_product: "" }, "-administered_at");
  const [record, setRecord] = useState<{ patient?: number } | null>(null);
  const canRecord = canVaccinate(user?.role) && !!user?.facility;

  useEffect(() => {
    const newFlag = params.get("new");
    const patient = params.get("patient");
    if (newFlag === "1") setRecord({ patient: patient ? Number(patient) : undefined });
    if (newFlag || patient) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<VaccinationRecord>[] = [
    {
      key: "patient",
      header: "Patient",
      render: (r) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{r.patient_name}</span>
          <span className="cell-sub mono">{r.patient_number}</span>
        </div>
      ),
    },
    { key: "vaccine", header: "Vaccine", render: (r) => <span className="cell-title">{r.vaccine_product_name}</span> },
    { key: "dose", header: "Dose", align: "right", render: (r) => <Badge tone="teal" dot={false}>#{r.dose_number}</Badge> },
    { key: "administered", header: "Administered", sortField: "administered_at", render: (r) => formatDateTime(r.administered_at) },
    { key: "batch", header: "Batch", render: (r) => <span className="mono" style={{ fontSize: 12.5 }}>{r.batch_number}</span> },
    { key: "by", header: "Recorded by", render: (r) => <span className="cell-sub">{r.recorded_by_username}</span> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Vaccination"
        title="Dose records"
        description="Every administered dose, linked to the patient, vaccine batch and stock movement."
        actions={canRecord && <Button icon="syringe" onClick={() => setRecord({})}>Record dose</Button>}
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search patient or vaccine…" />
          <div style={{ minWidth: 200, flex: "0 1 240px" }}>
            <ProductSelect value={list.filters.vaccine_product ? Number(list.filters.vaccine_product) : ""} onChange={(v) => list.setFilter("vaccine_product", v === "" ? "" : String(v))} category="VACCINE" placeholder="All vaccines" />
          </div>
          {list.filters.patient && <Button variant="ghost" size="sm" icon="x" onClick={() => list.setFilter("patient", "")}>Clear patient filter</Button>}
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(r) => r.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(r) => navigate(`/patients/${r.patient}`)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "syringe", title: "No doses recorded", message: "Recorded vaccinations will appear here.", action: canRecord ? <Button icon="syringe" onClick={() => setRecord({})}>Record dose</Button> : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
      {record && <RecordDoseModal presetPatient={record.patient} onClose={() => setRecord(null)} />}
    </div>
  );
}
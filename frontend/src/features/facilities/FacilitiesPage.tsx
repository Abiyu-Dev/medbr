import { useNavigate } from "react-router-dom";
import { FacilitiesApi } from "@/api/endpoints";
import type { Facility, FacilityStatus } from "@/api/types";
import { useList } from "@/hooks/useList";
import { Badge, Button, Card, DataTable, Icon, PageHeader, SearchBox, SelectInput, type Column } from "@/components/ui";
import { humanize } from "@/lib/formatters";

const STATUSES: FacilityStatus[] = ["APPROVED", "PENDING", "SUSPENDED", "REJECTED"];

export function FacilitiesPage() {
  const navigate = useNavigate();
  const list = useList<Facility>(["facilities"], FacilitiesApi.list, { status: "" }, "name");

  const columns: Column<Facility>[] = [
    {
      key: "name",
      header: "Facility",
      render: (f) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{f.name}</span>
          <span className="cell-sub">{f.town || f.region}{f.registration_number ? ` · ${f.registration_number}` : ""}</span>
        </div>
      ),
    },
    { key: "type", header: "Type", render: (f) => f.facility_type_display || humanize(f.facility_type) },
    { key: "region", header: "Region", render: (f) => f.region },
    { key: "status", header: "Status", render: (f) => <Badge value={f.status}>{f.status_display}</Badge> },
    {
      key: "capabilities",
      header: "Capabilities",
      render: (f) => (
        <div className="row" style={{ gap: 8 }}>
          {f.has_cold_chain && <span title="Cold chain" style={{ color: "var(--blue)" }}><Icon name="snowflake" size={16} /></span>}
          {f.provides_vaccination_services && <span title="Vaccination services" style={{ color: "var(--brand)" }}><Icon name="syringe" size={16} /></span>}
          {!f.has_cold_chain && !f.provides_vaccination_services && <span className="muted">—</span>}
        </div>
      ),
    },
    { key: "phone", header: "Contact", render: (f) => <span className="cell-sub">{f.contact_phone || "—"}</span> },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Network"
        title="Facilities"
        description="Every facility in the MedBridge network, with approval status and capabilities."
        actions={<Button variant="secondary" icon="map" onClick={() => navigate("/map")}>Map view</Button>}
      />
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search facilities…" />
          <SelectInput value={list.filters.status ?? ""} onChange={(e) => list.setFilter("status", e.target.value)} style={{ width: "auto" }}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </SelectInput>
        </div>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(f) => f.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={(f) => navigate(`/facilities/${f.id}`)}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "building", title: "No facilities found", message: "No facilities match your filters." }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>
    </div>
  );
}
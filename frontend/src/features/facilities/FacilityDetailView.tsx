import type { Facility } from "@/api/types";
import { Badge, Card, CardBody, CardHeader, Icon } from "@/components/ui";
import { FacilityMap } from "@/components/map/Maps";
import { formatDate, humanize } from "@/lib/formatters";

export function FacilityDetailView({ facility }: { facility: Facility }) {
  const hasCoords = !!facility.latitude && !!facility.longitude;
  return (
    <div className="stack">
      <Card>
        <CardHeader
          title="Facility profile"
          subtitle={`${facility.facility_type_display || humanize(facility.facility_type)} · ${facility.region}`}
          icon="building"
          action={<Badge value={facility.status}>{facility.status_display}</Badge>}
        />
        <CardBody>
          <div className="row wrap" style={{ gap: 8, marginBottom: 16 }}>
            {facility.has_cold_chain && <Badge tone="blue" dot={false}><Icon name="snowflake" size={13} /> Cold chain</Badge>}
            {facility.provides_vaccination_services && <Badge tone="teal" dot={false}><Icon name="syringe" size={13} /> Vaccination services</Badge>}
            {!facility.is_active && <Badge tone="slate" dot={false}>Inactive</Badge>}
          </div>
          <div className="detail-grid">
            <div className="detail-item"><div className="dt">Region</div><div className="dd">{facility.region || "—"}</div></div>
            <div className="detail-item"><div className="dt">Zone</div><div className="dd">{facility.zone || "—"}</div></div>
            <div className="detail-item"><div className="dt">Woreda</div><div className="dd">{facility.woreda || "—"}</div></div>
            <div className="detail-item"><div className="dt">Kebele</div><div className="dd">{facility.kebele || "—"}</div></div>
            <div className="detail-item"><div className="dt">Town / City</div><div className="dd">{facility.town || "—"}</div></div>
            <div className="detail-item"><div className="dt">Registration no.</div><div className="dd">{facility.registration_number || "—"}</div></div>
            <div className="detail-item"><div className="dt">Address</div><div className="dd">{facility.address || "—"}</div></div>
            <div className="detail-item"><div className="dt">Landmark</div><div className="dd">{facility.landmark || "—"}</div></div>
            <div className="detail-item"><div className="dt">Contact phone</div><div className="dd">{facility.contact_phone || "—"}</div></div>
            <div className="detail-item"><div className="dt">Contact email</div><div className="dd">{facility.contact_email || "—"}</div></div>
            <div className="detail-item"><div className="dt">Coordinates</div><div className="dd mono">{hasCoords ? `${facility.latitude}, ${facility.longitude}` : "—"}</div></div>
            <div className="detail-item"><div className="dt">Created</div><div className="dd">{formatDate(facility.created_at)}</div></div>
          </div>
          {facility.storage_capacity_notes && (
            <div className="detail-item" style={{ marginTop: 14 }}><div className="dt">Storage capacity</div><div className="dd">{facility.storage_capacity_notes}</div></div>
          )}
          {facility.has_cold_chain && facility.cold_chain_notes && (
            <div className="detail-item" style={{ marginTop: 10 }}><div className="dt">Cold-chain notes</div><div className="dd">{facility.cold_chain_notes}</div></div>
          )}
        </CardBody>
      </Card>

      {hasCoords && (
        <Card>
          <CardHeader title="Location" subtitle="Map pin used for transfer coordination" icon="pin" />
          <CardBody tight>
            <FacilityMap
              points={[{ id: facility.id, name: facility.name, facility_type: facility.facility_type, region: facility.region, latitude: facility.latitude!, longitude: facility.longitude! }]}
              height={300}
            />
          </CardBody>
        </Card>
      )}

      {(facility.submitted_by_username || facility.reviewed_by_username || facility.review_note) && (
        <Card>
          <CardHeader title="Review history" icon="clipboard" />
          <CardBody>
            <div className="detail-grid">
              <div className="detail-item"><div className="dt">Submitted by</div><div className="dd">{facility.submitted_by_username || "—"}</div></div>
              <div className="detail-item"><div className="dt">Reviewed by</div><div className="dd">{facility.reviewed_by_username || "—"}</div></div>
              <div className="detail-item"><div className="dt">Reviewed at</div><div className="dd">{formatDate(facility.reviewed_at)}</div></div>
            </div>
            {facility.review_note && <div className="detail-item" style={{ marginTop: 12 }}><div className="dt">Review note</div><div className="dd">{facility.review_note}</div></div>}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
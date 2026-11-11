import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { FacilityMap } from "@/components/map/Maps";
import { Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Icon, LoadingState, PageHeader } from "@/components/ui";
import { humanize } from "@/lib/formatters";

export function FacilityMapPage() {
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["facilities", "map"], queryFn: FacilitiesApi.map, staleTime: 120_000 });
  const points = q.data ?? [];
  const selected = points.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Coordination"
        title="Facility map"
        description="Geographic view of the network. Select a pin to inspect a facility."
        actions={<Button variant="secondary" icon="refresh" onClick={() => q.refetch()}>Refresh</Button>}
      />
      {q.isLoading ? (
        <LoadingState label="Loading map…" />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : points.length === 0 ? (
        <Card><EmptyState icon="map" title="No mapped facilities" message="Facilities with coordinates will appear here." /></Card>
      ) : (
        <div className="grid-2-1">
          <Card>
            <CardBody tight>
              <FacilityMap points={points} selectedId={selectedId} onSelect={setSelectedId} height={520} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Facilities" subtitle={`${points.length} mapped`} icon="building" />
            <CardBody tight>
              <div style={{ maxHeight: 460, overflowY: "auto" }}>
                {points.map((p) => (
                  <button
                    key={p.id}
                    className="dropdown-item"
                    onClick={() => setSelectedId(p.id)}
                    style={p.id === selectedId ? { background: "var(--brand-050)" } : undefined}
                  >
                    <span className="dropdown-icon" style={{ background: p.id === selectedId ? "var(--brand)" : "var(--brand-050)", color: p.id === selectedId ? "#fff" : "var(--brand)" }}>
                      <Icon name="pin" size={16} />
                    </span>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className="cell-title truncate" style={{ display: "block" }}>{p.name}</span>
                      <span className="cell-sub" style={{ display: "block" }}>{humanize(p.facility_type)} · {p.region}</span>
                    </span>
                  </button>
                ))}
              </div>
              {selected && (
                <div style={{ padding: 12, borderTop: "1px solid var(--border)" }}>
                  <Button block icon="arrow-right" onClick={() => navigate(`/facilities/${selected.id}`)}>Open {selected.name}</Button>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
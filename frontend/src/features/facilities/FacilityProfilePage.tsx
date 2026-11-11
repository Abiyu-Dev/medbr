import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { isManager, isAdmin } from "@/lib/permissions";
import { Button, EmptyState, ErrorState, Icon, LoadingState, PageHeader } from "@/components/ui";
import { FacilityDetailView } from "./FacilityDetailView";
import { FacilityEditModal } from "./FacilityEditModal";

export function FacilityProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const facilityId = user?.facility ?? null;
  const q = useQuery({
    queryKey: ["facility", facilityId],
    queryFn: () => FacilitiesApi.get(facilityId as number),
    enabled: !!facilityId,
    staleTime: 60_000,
  });
  const [edit, setEdit] = useState(false);
  const canEdit = isManager(user?.role) || isAdmin(user?.role);

  if (!facilityId) return <EmptyState icon="building" title="No facility assigned" message="Your account is not linked to a facility." />;
  if (q.isLoading) return <LoadingState label="Loading facility profile…" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const facility = q.data;

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Facility"
        title={facility.name}
        description="Your facility's operational profile, location and capabilities."
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            {isManager(user?.role) && <Button variant="secondary" icon="users" onClick={() => navigate("/users")}>Staff &amp; users</Button>}
            {canEdit && facility.status === "APPROVED" && <Button icon="edit" onClick={() => setEdit(true)}>Edit profile</Button>}
          </div>
        }
      />
      {facility.status !== "APPROVED" && (
        <div className={`alert ${facility.status === "REJECTED" ? "alert-danger" : "alert-warning"}`}>
          <Icon name="alert" size={17} />
          <span>
            <strong>This facility is {facility.status.toLowerCase()}. </strong>
            {facility.status === "PENDING" && "Operational features unlock once a central coordinator approves the application."}
            {facility.status === "REJECTED" && (facility.review_note || "Contact the central coordination team for details.")}
            {facility.status === "SUSPENDED" && "Contact the central coordination team to restore access."}
          </span>
        </div>
      )}
      <FacilityDetailView facility={facility} />
      {edit && <FacilityEditModal facility={facility} onClose={() => setEdit(false)} />}
    </div>
  );
}
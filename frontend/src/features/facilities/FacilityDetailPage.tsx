import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { isAdmin } from "@/lib/permissions";
import { Button, ErrorState, Field, LoadingState, Modal, PageHeader, TextArea, useToast } from "@/components/ui";
import { FacilityDetailView } from "./FacilityDetailView";

export function FacilityDetailPage() {
  const { id } = useParams();
  const facilityId = Number(id);
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [suspend, setSuspend] = useState(false);
  const [note, setNote] = useState("");

  const q = useQuery({
    queryKey: ["facilities", facilityId],
    queryFn: () => FacilitiesApi.get(facilityId),
    enabled: Number.isFinite(facilityId),
  });

  const suspendMutation = useMutation({
    mutationFn: () => FacilitiesApi.suspend(facilityId, note.trim() || undefined),
    onSuccess: () => {
      toast.success("Facility suspended", "Operational access has been revoked.");
      qc.invalidateQueries({ queryKey: ["facilities"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setSuspend(false);
      q.refetch();
    },
    onError: (e) => toast.error("Could not suspend", isApiError(e) ? e.detail : "Something went wrong."),
  });

  if (q.isLoading) return <LoadingState label="Loading facility…" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const facility = q.data;

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Network · Facility"
        title={facility.name}
        description={`${facility.facility_type_display || facility.region} · ${facility.region}`}
        actions={
          <div className="row wrap" style={{ gap: 8 }}>
            <Button variant="ghost" icon="chevron-left" onClick={() => navigate("/facilities")}>All facilities</Button>
            {facility.status === "PENDING" && <Button variant="secondary" icon="clipboard" onClick={() => navigate("/applications")}>Review application</Button>}
            {isAdmin(user?.role) && <Button variant="secondary" icon="users" onClick={() => navigate(`/users?facility=${facility.id}`)}>Staff</Button>}
            {isAdmin(user?.role) && facility.status === "APPROVED" && <Button variant="danger" icon="ban" onClick={() => setSuspend(true)}>Suspend</Button>}
          </div>
        }
      />
      <FacilityDetailView facility={facility} />

      <Modal
        open={suspend}
        onClose={() => setSuspend(false)}
        title="Suspend facility"
        subtitle={facility.name}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSuspend(false)} disabled={suspendMutation.isPending}>Cancel</Button>
            <Button variant="danger" loading={suspendMutation.isPending} onClick={() => suspendMutation.mutate()}>Suspend facility</Button>
          </>
        }
      >
        <div className="stack" style={{ gap: 14 }}>
          <div className="alert alert-danger">
            Suspending revokes this facility's operational access. Staff will be gated until it is re-approved.
          </div>
          <Field label="Review note" help="Optional — recorded in the audit log and shown to the facility.">
            <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason for suspension…" />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
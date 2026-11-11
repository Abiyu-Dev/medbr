import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { Facility } from "@/api/types";
import { useList } from "@/hooks/useList";
import { Badge, Button, Card, ConfirmDialog, DataTable, Drawer, Field, Modal, PageHeader, Tabs, TextArea, useToast, type Column } from "@/components/ui";
import { formatDate, humanize } from "@/lib/formatters";
import { FacilityDetailView } from "./FacilityDetailView";

export function ApplicationsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState("PENDING");
  const list = useList<Facility>(["applications"], FacilitiesApi.applications, { status: "PENDING" }, "-created_at");
  const [selected, setSelected] = useState<Facility | null>(null);
  const [approve, setApprove] = useState<Facility | null>(null);
  const [reject, setReject] = useState<Facility | null>(null);
  const [note, setNote] = useState("");

  function changeTab(key: string) {
    setTab(key);
    list.setFilter("status", key === "ALL" ? "" : key);
  }

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["applications"] });
    qc.invalidateQueries({ queryKey: ["facilities"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const approveMutation = useMutation({
    mutationFn: (f: Facility) => FacilitiesApi.approve(f.id, note.trim() || undefined),
    onSuccess: (_, f) => {
      toast.success("Application approved", `${f.name} can now operate on MedBridge.`);
      invalidate();
      setApprove(null);
      setSelected(null);
      setNote("");
    },
    onError: (e) => toast.error("Could not approve", isApiError(e) ? e.detail : "Something went wrong."),
  });

  const rejectMutation = useMutation({
    mutationFn: (f: Facility) => FacilitiesApi.reject(f.id, note.trim()),
    onSuccess: (_, f) => {
      toast.success("Application rejected", `${f.name} has been notified.`);
      invalidate();
      setReject(null);
      setSelected(null);
      setNote("");
    },
    onError: (e) => toast.error("Could not reject", isApiError(e) ? e.detail : "Something went wrong."),
  });

  const columns: Column<Facility>[] = [
    {
      key: "name",
      header: "Facility",
      render: (f) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{f.name}</span>
          <span className="cell-sub">{f.facility_type_display || humanize(f.facility_type)} · {f.region}</span>
        </div>
      ),
    },
    { key: "town", header: "Town", render: (f) => f.town || "—" },
    { key: "by", header: "Submitted by", render: (f) => f.submitted_by_username || "—" },
    { key: "date", header: "Submitted", sortField: "created_at", render: (f) => formatDate(f.created_at) },
    { key: "status", header: "Status", render: (f) => <Badge value={f.status}>{f.status_display}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (f) => f.status === "PENDING" ? (
        <div className="row" style={{ gap: 6, justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
          <Button variant="success" size="sm" icon="check" onClick={() => { setNote(""); setApprove(f); }}>Approve</Button>
          <Button variant="danger" size="sm" icon="x" onClick={() => { setNote(""); setReject(f); }}>Reject</Button>
        </div>
      ) : null,
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Network"
        title="Facility applications"
        description="Review onboarding requests. Approving grants a facility operational access."
      />
      <Tabs
        items={[
          { key: "PENDING", label: "Pending" },
          { key: "APPROVED", label: "Approved" },
          { key: "REJECTED", label: "Rejected" },
          { key: "ALL", label: "All" },
        ]}
        active={tab}
        onChange={changeTab}
      />
      <Card>
        <DataTable
          columns={columns}
          rows={list.rows}
          rowKey={(f) => f.id}
          isLoading={list.query.isLoading}
          error={list.query.error}
          onRetry={() => list.query.refetch()}
          onRowClick={setSelected}
          ordering={list.ordering}
          onSort={list.setOrdering}
          empty={{ icon: "clipboard", title: tab === "PENDING" ? "No pending applications" : "No applications", message: tab === "PENDING" ? "New facility onboarding requests will appear here." : undefined }}
          pagination={{ page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage }}
        />
      </Card>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""} subtitle="Application detail" wide>
        {selected && (
          <div className="stack">
            {selected.status === "PENDING" && (
              <div className="row wrap" style={{ gap: 8 }}>
                <Button variant="success" icon="check" onClick={() => { setNote(""); setApprove(selected); }}>Approve facility</Button>
                <Button variant="danger" icon="x" onClick={() => { setNote(""); setReject(selected); }}>Reject</Button>
              </div>
            )}
            <FacilityDetailView facility={selected} />
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={!!approve}
        onClose={() => setApprove(null)}
        onConfirm={() => approve && approveMutation.mutate(approve)}
        title="Approve facility"
        message={<>Approve <strong>{approve?.name}</strong>? The facility and its staff will gain operational access immediately.</>}
        confirmLabel="Approve"
        loading={approveMutation.isPending}
      />

      <Modal
        open={!!reject}
        onClose={() => setReject(null)}
        title="Reject application"
        subtitle={reject?.name}
        footer={
          <>
            <Button variant="secondary" onClick={() => setReject(null)} disabled={rejectMutation.isPending}>Cancel</Button>
            <Button variant="danger" loading={rejectMutation.isPending} disabled={note.trim() === ""} onClick={() => reject && rejectMutation.mutate(reject)}>Reject application</Button>
          </>
        }
      >
        <Field label="Rejection reason" required help="Required — shared with the applicant and recorded in the audit log.">
          <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Explain why this application is being rejected…" />
        </Field>
      </Modal>
    </div>
  );
}
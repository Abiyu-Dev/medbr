import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { VaccinationApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { FollowUpStatus, VaccineFollowUp } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useList } from "@/hooks/useList";
import { canVaccinate } from "@/lib/permissions";
import { Badge, Button, Card, DataTable, Drawer, Field, Icon, Modal, PageHeader, SearchBox, SelectInput, Tabs, TextArea, TextInput, useToast, type Column } from "@/components/ui";
import { PatientSelect, ProductSelect } from "@/components/forms/Pickers";
import { daysUntil, formatDate, formatDateTime, humanize } from "@/lib/formatters";
import { FollowUpActionModal, type FollowUpAction } from "./FollowUpActionModal";

const STATUS_OPTIONS: FollowUpStatus[] = [
  "UPCOMING", "DUE", "OVERDUE", "CONTACT_ATTEMPTED", "REVIEW_REQUIRED", "COMPLETED", "CANCELLED",
];
const isTerminal = (s: FollowUpStatus) => s === "COMPLETED" || s === "CANCELLED";

function ScheduleFollowUpModal({ presetPatient, onClose }: { presetPatient?: number | null; onClose: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [patient, setPatient] = useState<number | null>(presetPatient ?? null);
  const [product, setProduct] = useState<number | "">("");
  const [dose, setDose] = useState("1");
  const [dueDate, setDueDate] = useState("");
  const [assignMode, setAssignMode] = useState<"none" | "me" | "other">("none");
  const [otherId, setOtherId] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const assignedTo = assignMode === "me" ? user?.id : assignMode === "other" ? Number(otherId) : undefined;
  const mutation = useMutation({
    mutationFn: () =>
      VaccinationApi.createFollowup({
        patient,
        vaccine_product: product,
        dose_number: Number(dose),
        due_date: dueDate,
        assigned_to: assignedTo ?? undefined,
      }),
    onSuccess: (data) => {
      toast.success("Follow-up scheduled", `${data.patient_name} · ${data.vaccine_product_name} dose ${data.dose_number} due ${formatDate(data.due_date)}`);
      qc.invalidateQueries({ queryKey: ["followups"] });
      qc.invalidateQueries({ queryKey: ["due-followups"] });
      qc.invalidateQueries({ queryKey: ["overdue-followups"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Could not schedule", e.detail); }
      else toast.error("Could not schedule", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const doseNum = Number(dose);
  const valid =
    patient !== null && product !== "" && Number.isInteger(doseNum) && doseNum >= 1 && dueDate !== "" &&
    (assignMode !== "other" || (Number.isInteger(Number(otherId)) && Number(otherId) > 0));

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Schedule a follow-up"
      subtitle="Manually add a dose reminder to the follow-up queue."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button icon="calendar" loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Schedule follow-up</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="alert alert-info"><Icon name="info" size={16} /><span>Follow-ups are normally created automatically when you record a dose that has a next-in-series. Use this to add a reminder manually.</span></div>
        <Field label="Patient" required error={fe("patient")}>
          <PatientSelect value={patient} onChange={setPatient} invalid={!!fe("patient")} />
        </Field>
        <div className="field-row">
          <Field label="Vaccine" required error={fe("vaccine_product")}>
            <ProductSelect value={product} onChange={setProduct} category="VACCINE" placeholder="Select vaccine…" invalid={!!fe("vaccine_product")} />
          </Field>
          <Field label="Dose number" required error={fe("dose_number")}>
            <TextInput type="number" min={1} step={1} value={dose} onChange={(e) => setDose(e.target.value)} invalid={!!fe("dose_number")} />
          </Field>
        </div>
        <Field label="Due date" required error={fe("due_date")}>
          <TextInput type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} invalid={!!fe("due_date")} />
        </Field>
        <Field label="Assign to" error={fe("assigned_to")} help="Optional — the staff member responsible for contacting the patient.">
          <SelectInput value={assignMode} onChange={(e) => setAssignMode(e.target.value as "none" | "me" | "other")}>
            <option value="none">Unassigned</option>
            <option value="me">Me — {user?.username}</option>
            <option value="other">Another user (ID)</option>
          </SelectInput>
        </Field>
        {assignMode === "other" && (
          <Field label="User ID" required error={fe("assigned_to")}>
            <TextInput type="number" min={1} step={1} value={otherId} onChange={(e) => setOtherId(e.target.value)} placeholder="e.g. 7" />
          </Field>
        )}
      </div>
    </Modal>
  );
}

function FollowUpDrawer({ followUp: initial, canAct, onClose }: { followUp: VaccineFollowUp; canAct: boolean; onClose: () => void }) {
  const [f, setF] = useState(initial);
  const [action, setAction] = useState<FollowUpAction | null>(null);
  const terminal = isTerminal(f.effective_status);
  const d = daysUntil(f.due_date);

  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title={`${f.vaccine_product_name} · dose ${f.dose_number}`}
      subtitle={<Link to={`/patients/${f.patient}`} style={{ color: "var(--brand)", fontWeight: 600 }}>{f.patient_name} · {f.patient_number}</Link>}
      footer={
        canAct && !terminal ? (
          <>
            <Button variant="secondary" icon="ban" onClick={() => setAction("cancel")}>Cancel</Button>
            <Button variant="secondary" icon="alert" onClick={() => setAction("review")}>Mark review</Button>
            <Button icon="phone" onClick={() => setAction("contact")}>Record contact</Button>
          </>
        ) : <Button variant="secondary" onClick={onClose}>Close</Button>
      }
    >
      <div className="stack" style={{ gap: 18 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <Badge value={f.effective_status}>{humanize(f.effective_status)}</Badge>
          <Badge tone="teal" dot={false}>Dose #{f.dose_number}</Badge>
          {f.assigned_to_username && <span className="chip"><Icon name="user" size={13} /> {f.assigned_to_username}</span>}
        </div>

        {!terminal && d !== null && (
          <div className={`alert ${d < 0 ? "alert-danger" : d <= 7 ? "alert-warning" : "alert-info"}`} style={{ alignItems: "center" }}>
            <Icon name="clock" size={20} />
            <div>
              <strong>{d < 0 ? `${-d} day${-d === 1 ? "" : "s"} overdue` : d === 0 ? "Due today" : `Due in ${d} day${d === 1 ? "" : "s"}`}</strong>
              <div style={{ fontSize: 12.5, marginTop: 2 }}>Due date {formatDate(f.due_date)}. Status shown is time-aware (effective status).</div>
            </div>
          </div>
        )}

        <div className="detail-grid">
          <div className="detail-item"><div className="dt">Due date</div><div className="dd">{formatDate(f.due_date)}</div></div>
          <div className="detail-item"><div className="dt">Effective status</div><div className="dd">{humanize(f.effective_status)}</div></div>
          <div className="detail-item"><div className="dt">Assigned to</div><div className="dd">{f.assigned_to_username || "Unassigned"}</div></div>
          <div className="detail-item"><div className="dt">Last contacted</div><div className="dd">{formatDateTime(f.last_contacted_at)}</div></div>
          <div className="detail-item"><div className="dt">Contact outcome</div><div className="dd">{f.contact_outcome_display || humanize(f.contact_outcome) || "—"}</div></div>
          <div className="detail-item"><div className="dt">Next action date</div><div className="dd">{formatDate(f.next_action_date)}</div></div>
          <div className="detail-item"><div className="dt">Created</div><div className="dd">{formatDate(f.created_at)}</div></div>
          <div className="detail-item"><div className="dt">Updated</div><div className="dd">{formatDate(f.updated_at)}</div></div>
        </div>

        {f.review_reason && (
          <div className="detail-item"><div className="dt">Review reason</div><div className="dd" style={{ fontWeight: 400, lineHeight: 1.6 }}>{f.review_reason}</div></div>
        )}
        {terminal && (
          <div className="alert alert-info"><Icon name="info" size={16} /><span>This follow-up is {humanize(f.effective_status).toLowerCase()} and can no longer be actioned.</span></div>
        )}
      </div>
      {action && <FollowUpActionModal action={action} followUp={f} onClose={() => setAction(null)} onDone={setF} />}
    </Drawer>
  );
}

export function FollowUpsPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const initialPatient = params.get("patient") ?? "";
  const initialStatus = params.get("status") ?? "";
  const requestedTab = params.get("tab");
  const hasFacility = !!user?.facility;
  const canAct = canVaccinate(user?.role);
  const canCreate = canAct && hasFacility;

  const [tab, setTab] = useState<string>(
    hasFacility && (requestedTab === "due" || requestedTab === "overdue") ? requestedTab : "all",
  );
  const list = useList<VaccineFollowUp>(
    ["followups"], VaccinationApi.followups,
    { patient: initialPatient, status: initialStatus, vaccine_product: "" }, "due_date",
  );
  const due = useQuery({ queryKey: ["due-followups"], queryFn: VaccinationApi.due, enabled: hasFacility });
  const overdue = useQuery({ queryKey: ["overdue-followups"], queryFn: VaccinationApi.overdue, enabled: hasFacility });
  const [selected, setSelected] = useState<VaccineFollowUp | null>(null);
  const [schedule, setSchedule] = useState(false);

  useEffect(() => {
    if (params.get("patient") || params.get("status") || params.get("tab")) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const needle = list.search.trim().toLowerCase();
  const vax = list.filters.vaccine_product;
  const matches = (f: VaccineFollowUp) =>
    (!needle || f.patient_name.toLowerCase().includes(needle) || f.patient_number.toLowerCase().includes(needle) || f.vaccine_product_name.toLowerCase().includes(needle)) &&
    (!vax || f.vaccine_product === Number(vax));

  const sourceRows = tab === "all" ? list.rows : tab === "due" ? (due.data?.follow_ups ?? []) : (overdue.data?.follow_ups ?? []);
  const rows = tab === "all" ? sourceRows : sourceRows.filter(matches);
  const isLoading = tab === "all" ? list.query.isLoading : tab === "due" ? due.isLoading : overdue.isLoading;
  const error = tab === "all" ? list.query.error : tab === "due" ? due.error : overdue.error;
  const onRetry = tab === "all" ? () => list.query.refetch() : tab === "due" ? () => due.refetch() : () => overdue.refetch();

  const tabs = [
    { key: "all", label: "All", count: list.count },
    ...(hasFacility ? [
      { key: "due", label: "Due soon", count: due.data?.count },
      { key: "overdue", label: "Overdue", count: overdue.data?.count },
    ] : []),
  ];

  const columns: Column<VaccineFollowUp>[] = [
    {
      key: "patient", header: "Patient",
      render: (f) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title">{f.patient_name}</span>
          <span className="cell-sub mono">{f.patient_number}</span>
        </div>
      ),
    },
    {
      key: "vaccine", header: "Vaccine / dose",
      render: (f) => (
        <div className="stack" style={{ gap: 2 }}>
          <span className="cell-title" style={{ fontSize: 13 }}>{f.vaccine_product_name}</span>
          <span className="cell-sub">Dose #{f.dose_number}</span>
        </div>
      ),
    },
    {
      key: "due", header: "Due date", sortField: "due_date",
      render: (f) => {
        const dd = daysUntil(f.due_date);
        return (
          <div className="stack" style={{ gap: 2 }}>
            <span>{formatDate(f.due_date)}</span>
            {dd !== null && !isTerminal(f.effective_status) && (
              <span className="cell-sub" style={{ color: dd < 0 ? "var(--red)" : dd <= 7 ? "var(--amber)" : "var(--muted)" }}>
                {dd < 0 ? `${-dd}d overdue` : dd === 0 ? "today" : `in ${dd}d`}
              </span>
            )}
          </div>
        );
      },
    },
    { key: "status", header: "Status", sortField: "status", render: (f) => <Badge value={f.effective_status}>{humanize(f.effective_status)}</Badge> },
    { key: "assigned", header: "Assigned", render: (f) => f.assigned_to_username || <span className="faint">Unassigned</span> },
    { key: "contact", header: "Last contact", render: (f) => f.last_contacted_at ? <span className="cell-sub">{formatDate(f.last_contacted_at)}</span> : <span className="faint">—</span> },
  ];

  const empty =
    tab === "due"
      ? { icon: "calendar" as const, title: "Nothing due soon", message: "No follow-ups are due within the next 7 days." }
      : tab === "overdue"
        ? { icon: "check-circle" as const, title: "No overdue follow-ups", message: "Every past-due follow-up has been completed or cancelled." }
        : { icon: "calendar" as const, title: "No follow-ups", message: "Follow-ups are created automatically when a dose with a next-in-series is recorded." };

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Vaccination"
        title="Follow-ups"
        description="Dose reminders for the vaccination series. Status is time-aware: a follow-up becomes due or overdue automatically as its date passes."
        actions={canCreate && <Button icon="plus" onClick={() => setSchedule(true)}>Schedule follow-up</Button>}
      />
      <Tabs items={tabs} active={tab} onChange={setTab} />
      {tab === "due" && due.data && (
        <div className="alert alert-info"><Icon name="clock" size={16} /><span>Due within {due.data.window_days ?? 7} days, as of <strong>{formatDate(due.data.as_of)}</strong>. {due.data.count} follow-up{due.data.count === 1 ? "" : "s"} in this window.</span></div>
      )}
      {tab === "overdue" && overdue.data && (
        <div className="alert alert-warning"><Icon name="alert" size={16} /><span>Past due as of <strong>{formatDate(overdue.data.as_of)}</strong>. {overdue.data.count} follow-up{overdue.data.count === 1 ? "" : "s"} need attention.</span></div>
      )}
      <Card>
        <div className="toolbar">
          <SearchBox value={list.search} onChange={list.setSearch} placeholder="Search patient or vaccine…" />
          <div style={{ minWidth: 180, flex: "0 1 220px" }}>
            <ProductSelect value={vax ? Number(vax) : ""} onChange={(v) => list.setFilter("vaccine_product", v === "" ? "" : String(v))} category="VACCINE" placeholder="All vaccines" />
          </div>
          {tab === "all" && (
            <SelectInput value={list.filters.status ?? ""} onChange={(e) => list.setFilter("status", e.target.value)} style={{ width: "auto" }}>
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </SelectInput>
          )}
          {list.filters.patient && <Button variant="ghost" size="sm" icon="x" onClick={() => list.setFilter("patient", "")}>Clear patient filter</Button>}
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(f) => f.id}
          isLoading={isLoading}
          error={error}
          onRetry={onRetry}
          onRowClick={(f) => setSelected(f)}
          ordering={tab === "all" ? list.ordering : undefined}
          onSort={tab === "all" ? list.setOrdering : undefined}
          empty={{ ...empty, action: canCreate ? <Button icon="plus" onClick={() => setSchedule(true)}>Schedule follow-up</Button> : undefined }}
          pagination={tab === "all" ? { page: list.page, count: list.count, pageSize: list.pageSize, onPageChange: list.setPage } : undefined}
        />
      </Card>
      {selected && <FollowUpDrawer followUp={selected} canAct={canAct} onClose={() => setSelected(null)} />}
      {schedule && <ScheduleFollowUpModal presetPatient={list.filters.patient ? Number(list.filters.patient) : null} onClose={() => setSchedule(false)} />}
    </div>
  );
}
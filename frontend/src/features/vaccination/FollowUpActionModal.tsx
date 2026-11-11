import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { VaccinationApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { ContactOutcome, VaccineFollowUp } from "@/api/types";
import { Button, Field, Icon, Modal, SelectInput, TextArea, TextInput, useToast } from "@/components/ui";
import { formatDate } from "@/lib/formatters";

export type FollowUpAction = "contact" | "review" | "cancel";

const OUTCOMES: { value: ContactOutcome; label: string }[] = [
  { value: "REACHED", label: "Reached" },
  { value: "NO_ANSWER", label: "No answer" },
  { value: "RESCHEDULED", label: "Rescheduled" },
  { value: "REFERRED_FOR_REVIEW", label: "Referred for review" },
];

export function FollowUpActionModal({
  action,
  followUp,
  onClose,
  onDone,
}: {
  action: FollowUpAction;
  followUp: VaccineFollowUp;
  onClose: () => void;
  onDone: (f: VaccineFollowUp) => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [outcome, setOutcome] = useState<ContactOutcome>("REACHED");
  const [notes, setNotes] = useState("");
  const [nextDate, setNextDate] = useState("");
  const [reason, setReason] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useMutation({
    mutationFn: () => {
      if (action === "contact")
        return VaccinationApi.contact(followUp.id, {
          outcome,
          notes: notes.trim() || undefined,
          next_action_date: outcome === "RESCHEDULED" ? nextDate : undefined,
        });
      if (action === "review") return VaccinationApi.markReview(followUp.id, reason.trim());
      return VaccinationApi.cancelFollowup(followUp.id, reason.trim() || undefined);
    },
    onSuccess: (data) => {
      const label = action === "contact" ? "Contact recorded" : action === "review" ? "Marked for review" : "Follow-up cancelled";
      toast.success(label, `${data.patient_name} · ${data.vaccine_product_name} dose ${data.dose_number}`);
      qc.invalidateQueries({ queryKey: ["followups"] });
      qc.invalidateQueries({ queryKey: ["due-followups"] });
      qc.invalidateQueries({ queryKey: ["overdue-followups"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone(data);
      onClose();
    },
    onError: (e) => {
      if (isApiError(e)) { setFieldErrors(e.fieldErrors ?? {}); toast.error("Action failed", e.detail); }
      else toast.error("Action failed", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const valid =
    action === "contact"
      ? outcome !== "RESCHEDULED" || nextDate !== ""
      : action === "review"
        ? reason.trim() !== ""
        : true;
  const title = action === "contact" ? "Record contact attempt" : action === "review" ? "Mark review required" : "Cancel follow-up";
  const confirm = action === "contact" ? "Save contact" : action === "review" ? "Mark for review" : "Cancel follow-up";

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      subtitle={`${followUp.patient_name} · ${followUp.vaccine_product_name} dose ${followUp.dose_number} · due ${formatDate(followUp.due_date)}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button variant={action === "cancel" ? "danger" : "primary"} loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>{confirm}</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {action === "contact" && (
          <>
            <Field label="Outcome" required error={fe("outcome")}>
              <SelectInput value={outcome} onChange={(e) => setOutcome(e.target.value as ContactOutcome)}>
                {OUTCOMES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </SelectInput>
            </Field>
            {outcome === "RESCHEDULED" && (
              <Field label="New due date" required error={fe("next_action_date")} help="The follow-up returns to upcoming with this due date.">
                <TextInput type="date" value={nextDate} onChange={(e) => setNextDate(e.target.value)} invalid={!!fe("next_action_date")} />
              </Field>
            )}
            {outcome === "REFERRED_FOR_REVIEW" && (
              <div className="alert alert-warning"><Icon name="alert" size={16} /><span>This flags the follow-up for clinical review.</span></div>
            )}
            <Field label="Notes" error={fe("notes")}>
              <TextArea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What was discussed on the call…" />
            </Field>
          </>
        )}
        {action === "review" && (
          <>
            <div className="alert alert-warning"><Icon name="alert" size={16} /><span>Flags this follow-up as requiring clinical review before the next dose.</span></div>
            <Field label="Reason" required error={fe("reason")}>
              <TextArea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why does this need review?" invalid={!!fe("reason")} />
            </Field>
          </>
        )}
        {action === "cancel" && (
          <>
            <div className="alert alert-info"><Icon name="info" size={16} /><span>Cancelling closes this follow-up. It will no longer appear in due or overdue queues.</span></div>
            <Field label="Reason" error={fe("reason")} help="Optional — recorded in the audit log.">
              <TextArea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this follow-up being cancelled?" />
            </Field>
          </>
        )}
      </div>
    </Modal>
  );
}
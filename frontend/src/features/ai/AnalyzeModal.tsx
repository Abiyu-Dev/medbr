import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AIApi } from "@/api/endpoints";
import { isApiError } from "@/api/client";
import type { AIAnalysisType } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useOwnFacility } from "@/hooks/useOwnFacility";
import { canRunInventoryAI, canRunVaccinationAI, isCentral } from "@/lib/permissions";
import { Button, Field, Icon, Modal, SelectInput, TextInput, useToast, type IconName } from "@/components/ui";
import { FacilitySelect } from "@/components/forms/Pickers";

const TYPE_INFO: Record<AIAnalysisType, { label: string; description: string; icon: IconName }> = {
  INVENTORY_ANALYSIS: { label: "Inventory analysis", description: "Stock risks and redistribution opportunities across the selected scope.", icon: "box" },
  SUPPLY_GAP_PRIORITIZATION: { label: "Supply-gap prioritization", description: "Rank the network's open supply gaps by urgency.", icon: "gap" },
  VACCINATION_DEMAND_SUMMARY: { label: "Vaccination demand", description: "Aggregate upcoming dose demand versus stock for a vaccination facility.", icon: "syringe" },
  TRANSFER_SOURCING: { label: "Transfer sourcing", description: "Planned donor transfers for open supply requests — run from the Supply Requests page.", icon: "truck" },
};

export function AnalyzeModal({
  onClose,
  initialType,
  initialFacilityId,
}: {
  onClose: () => void;
  initialType?: AIAnalysisType;
  initialFacilityId?: number | "";
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const central = isCentral(user?.role);
  const own = useOwnFacility();

  const available: AIAnalysisType[] = [];
  if (canRunInventoryAI(user?.role)) available.push("INVENTORY_ANALYSIS");
  if (central) available.push("SUPPLY_GAP_PRIORITIZATION");
  if (canRunVaccinationAI(user?.role) && (central || own.providesVaccination)) available.push("VACCINATION_DEMAND_SUMMARY");

  const [type, setType] = useState<AIAnalysisType>(
    initialType && available.includes(initialType) ? initialType : (available[0] ?? "INVENTORY_ANALYSIS"),
  );
  const [facility, setFacility] = useState<number | "">(
    initialFacilityId ? initialFacilityId : central ? "" : (user?.facility ?? ""),
  );
  const [horizon, setHorizon] = useState("30");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const minHorizon = type === "VACCINATION_DEMAND_SUMMARY" ? 7 : 1;
  const h = Number(horizon);
  const horizonValid = Number.isInteger(h) && h >= minHorizon && h <= 180;
  const needsFacilityPick = type === "VACCINATION_DEMAND_SUMMARY" && central;
  const valid = available.length > 0 && horizonValid && (!needsFacilityPick || facility !== "");

  const mutation = useMutation({
    mutationFn: () => {
      if (type === "INVENTORY_ANALYSIS")
        return AIApi.analyzeInventory({ facility: central && facility !== "" ? Number(facility) : undefined, horizon_days: h });
      if (type === "SUPPLY_GAP_PRIORITIZATION")
        return AIApi.prioritizeGaps({ horizon_days: h });
      return AIApi.summarizeVaccination({ facility: central ? Number(facility) : (user?.facility as number), horizon_days: h });
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["ai-recommendations"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (data.status === "FAILED") toast.warning("Analysis failed", data.error || "The AI service was unavailable.");
      else toast.success("Analysis complete", `${TYPE_INFO[data.analysis_type].label} · ${data.status_display ?? data.status}`);
      onClose();
      navigate(`/ai/${data.id}`);
    },
    onError: (e) => {
      if (isApiError(e)) {
        setFieldErrors(e.fieldErrors ?? {});
        if (e.status === 429) toast.error("Rate limited", "AI analyses are limited to 20 per hour. Please try again later.");
        else toast.error("Could not run analysis", e.detail);
      } else toast.error("Could not run analysis", "Something went wrong.");
    },
  });
  const fe = (k: string) => fieldErrors[k];
  const showFacilityPicker = type !== "SUPPLY_GAP_PRIORITIZATION" && central;
  const pinnedFacility = type !== "SUPPLY_GAP_PRIORITIZATION" && !central;

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Run AI analysis"
      subtitle="Advisory only — a human must review the result."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button icon="sparkles" loading={mutation.isPending} disabled={!valid} onClick={() => mutation.mutate()}>Run analysis</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="alert alert-info"><Icon name="shield" size={16} /><span>The AI never moves stock or creates transfers. Its output is validated against live data and requires human approval. Analyses are limited to 20 per hour.</span></div>
        {available.length === 0 ? (
          <div className="alert alert-warning"><Icon name="alert" size={16} /><span>Your role cannot run AI analyses. You can still view recommendations shared with your facility.</span></div>
        ) : (
          <>
            <Field label="Analysis type" required>
              <SelectInput value={type} onChange={(e) => setType(e.target.value as AIAnalysisType)}>
                {available.map((t) => <option key={t} value={t}>{TYPE_INFO[t].label}</option>)}
              </SelectInput>
            </Field>
            <div className="row" style={{ gap: 10, alignItems: "flex-start", padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--r-md)", border: "1px solid var(--border)" }}>
              <Icon name={TYPE_INFO[type].icon} size={18} />
              <span className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>{TYPE_INFO[type].description}</span>
            </div>
            {showFacilityPicker && (
              <Field label={type === "VACCINATION_DEMAND_SUMMARY" ? "Facility" : "Scope"} required={type === "VACCINATION_DEMAND_SUMMARY"} error={fe("facility")} help={type === "INVENTORY_ANALYSIS" ? "Leave blank to analyse the whole network." : "The vaccination facility to summarise."}>
                <FacilitySelect value={facility} onChange={setFacility} placeholder={type === "INVENTORY_ANALYSIS" ? "Nationwide — all facilities" : "Select facility…"} invalid={!!fe("facility")} />
              </Field>
            )}
            {pinnedFacility && (
              <Field label="Scope">
                <TextInput value={own.facility?.name ?? user?.facility_name ?? "Your facility"} disabled />
              </Field>
            )}
            {type === "SUPPLY_GAP_PRIORITIZATION" && (
              <div className="alert alert-info"><Icon name="globe" size={16} /><span>Prioritizes all open supply gaps across the network. Requires at least one open gap.</span></div>
            )}
            <Field label="Horizon (days)" required error={fe("horizon_days")} help={`Projection window, ${minHorizon}–180 days.`}>
              <TextInput type="number" min={minHorizon} max={180} step={1} value={horizon} onChange={(e) => setHorizon(e.target.value)} invalid={!!fe("horizon_days") || !horizonValid} />
            </Field>
          </>
        )}
      </div>
    </Modal>
  );
}
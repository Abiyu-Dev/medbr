import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import { FacilitySelect } from "@/components/forms/Pickers";
import { Icon } from "@/components/ui";

export function useInventoryScope() {
  const { user } = useAuth();
  const central = isCentral(user?.role);
  const [facilityId, setFacilityId] = useState<number | "">("");
  const facilities = useQuery({
    queryKey: ["facilities", "inventory-scope"],
    queryFn: () => FacilitiesApi.list({ ordering: "name" }),
    enabled: central,
    staleTime: 120_000,
  });
  useEffect(() => {
    if (central && facilityId === "" && facilities.data) {
      const first = facilities.data.results.find((f) => f.status === "APPROVED");
      if (first) setFacilityId(first.id);
    }
  }, [central, facilityId, facilities.data]);

  const params: Record<string, number> = central && facilityId !== "" ? { facility: facilityId } : {};
  const enabled = !central || facilityId !== "";
  return { central, facilityId, setFacilityId, params, enabled };
}

export function FacilityScopeBar({
  facilityId,
  onChange,
}: {
  facilityId: number | "";
  onChange: (v: number | "") => void;
}) {
  return (
    <div className="alert alert-info" style={{ alignItems: "center" }}>
      <Icon name="building" size={17} />
      <span style={{ flex: 1 }}>Viewing stock for a single facility. Choose one to load its summary.</span>
      <div style={{ minWidth: 240 }}>
        <FacilitySelect value={facilityId} onChange={onChange} placeholder="Select facility…" />
      </div>
    </div>
  );
}
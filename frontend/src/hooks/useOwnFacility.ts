import { useQuery } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import type { Facility } from "@/api/types";

export function useOwnFacility() {
  const { user } = useAuth();
  const facilityId = user?.facility ?? null;
  const query = useQuery({
    queryKey: ["facility", facilityId],
    queryFn: () => FacilitiesApi.get(facilityId as number),
    enabled: !!facilityId,
    staleTime: 60_000,
  });
  return {
    facility: (query.data as Facility | undefined) ?? null,
    isLoading: query.isLoading,
    facilityId,
    providesVaccination: query.data?.provides_vaccination_services ?? false,
    hasColdChain: query.data?.has_cold_chain ?? false,
  };
}
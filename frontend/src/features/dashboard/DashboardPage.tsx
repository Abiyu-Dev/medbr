import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import { CentralDashboard } from "./CentralDashboard";
import { FacilityDashboard } from "./FacilityDashboard";

export function DashboardPage() {
  const { user } = useAuth();
  return isCentral(user?.role) ? <CentralDashboard /> : <FacilityDashboard />;
}
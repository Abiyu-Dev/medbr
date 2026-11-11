import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";
import { AppShell } from "@/components/layout/AppShell";
import { OnboardingGate } from "@/features/onboarding/OnboardingGate";
import { FullLoader } from "@/components/ui";

export function ProtectedArea() {
  const { user, isLoading } = useAuth();

  if (isLoading) return <FullLoader />;
  if (!user) return <Navigate to="/login" replace />;

  // Central users operate network-wide and never need facility onboarding.
  if (isCentral(user.role)) return <AppShell />;

  // Facility users need an assigned, approved facility to reach operational pages.
  if (user.facility && user.facility_status === "APPROVED") return <AppShell />;

  return <OnboardingGate />;
}
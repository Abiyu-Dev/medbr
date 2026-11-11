import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { FullLoader } from "@/components/ui";
import { ProtectedArea } from "./ProtectedArea";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ProfilePage } from "@/features/profile/ProfilePage";
import { NotFoundPage } from "@/features/misc/NotFoundPage";
import { FacilitiesPage } from "@/features/facilities/FacilitiesPage";
import { FacilityDetailPage } from "@/features/facilities/FacilityDetailPage";
import { FacilityProfilePage } from "@/features/facilities/FacilityProfilePage";
import { ApplicationsPage } from "@/features/facilities/ApplicationsPage";
import { FacilityMapPage } from "@/features/facilities/FacilityMapPage";
import { UsersPage } from "@/features/facilities/UsersPage";
import { InventoryPage } from "@/features/inventory/InventoryPage";
import { BatchesPage } from "@/features/inventory/BatchesPage";
import { MovementsPage } from "@/features/inventory/MovementsPage";
import { ExpiringPage } from "@/features/inventory/ExpiringPage";
import { ShortagesPage } from "@/features/inventory/ShortagesPage";
import { EquipmentPage } from "@/features/inventory/EquipmentPage";
import { ProductsPage } from "@/features/products/ProductsPage";
import { TransfersPage } from "@/features/transfers/TransfersPage";
import { TransferDetailPage } from "@/features/transfers/TransferDetailPage";
import { SupplyGapsPage } from "@/features/supplygaps/SupplyGapsPage";
import { SupplyRequestsPage } from "@/features/supply/SupplyRequestsPage";
import { PatientsPage } from "@/features/vaccination/PatientsPage";
import { PatientDetailPage } from "@/features/vaccination/PatientDetailPage";
import { VaccinationRecordsPage } from "@/features/vaccination/VaccinationRecordsPage";
import { FollowUpsPage } from "@/features/vaccination/FollowUpsPage";
import { SchedulesPage } from "@/features/vaccination/SchedulesPage";
import { AIPage } from "@/features/ai/AIPage";
import { AIDetailPage } from "@/features/ai/AIDetailPage";
import { AuditPage } from "@/features/audit/AuditPage";

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <FullLoader />;
  if (user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
      <Route element={<ProtectedArea />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/facilities" element={<FacilitiesPage />} />
        <Route path="/facilities/:id" element={<FacilityDetailPage />} />
        <Route path="/facility" element={<FacilityProfilePage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/map" element={<FacilityMapPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/batches" element={<BatchesPage />} />
        <Route path="/movements" element={<MovementsPage />} />
        <Route path="/expiring" element={<ExpiringPage />} />
        <Route path="/shortages" element={<ShortagesPage />} />
        <Route path="/equipment" element={<EquipmentPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/transfers" element={<TransfersPage />} />
        <Route path="/transfers/:id" element={<TransferDetailPage />} />
        <Route path="/supply-gaps" element={<SupplyGapsPage />} />
        <Route path="/supply-requests" element={<SupplyRequestsPage />} />
        <Route path="/patients" element={<PatientsPage />} />
        <Route path="/patients/:id" element={<PatientDetailPage />} />
        <Route path="/vaccination-records" element={<VaccinationRecordsPage />} />
        <Route path="/followups" element={<FollowUpsPage />} />
        <Route path="/schedules" element={<SchedulesPage />} />
        <Route path="/ai" element={<AIPage />} />
        <Route path="/ai/:id" element={<AIDetailPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
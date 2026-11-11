import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { useOwnFacility } from "@/hooks/useOwnFacility";
import { useAuth } from "@/auth/AuthContext";
import { isCentral } from "@/lib/permissions";

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { user } = useAuth();
  const { providesVaccination } = useOwnFacility();
  const central = isCentral(user?.role);
  // Central coordinators can browse schedules; vaccination nav flag only matters for facility users.
  const showVaccination = central ? true : providesVaccination;

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        providesVaccination={showVaccination}
      />
      <div className="main-panel">
        <Topbar onMenu={() => setSidebarOpen(true)} />
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FacilitiesApi } from "@/api/endpoints";
import type { Facility } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button, Icon, Badge, LoadingState } from "@/components/ui";
import { ApplyForm } from "./ApplyForm";
import {
  clearStoredApplicationId,
  getStoredApplicationId,
  setStoredApplicationId,
} from "@/lib/application";
import { formatDate } from "@/lib/formatters";

function Frame({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  const { logout } = useAuth();
  return (
    <div className="public-page">
      <div className="row" style={{ gap: 12 }}>
        <div className="brand-mark"><Icon name="heart" size={22} /></div>
        <div className="brand-text">
          <strong style={{ color: "var(--ink)" }}>MedBridge</strong>
          <span>Ethiopia</span>
        </div>
      </div>
      <div className="public-card" style={wide ? { maxWidth: 820 } : undefined}>{children}</div>
      <button className="btn btn-ghost" style={{ marginTop: 20 }} onClick={logout}>
        <Icon name="logout" size={16} /> Sign out
      </button>
    </div>
  );
}

function StatusScreen({
  facility,
  tone,
  icon,
  title,
  children,
}: {
  facility: Facility;
  tone: "amber" | "red" | "slate";
  icon: "clock" | "x-circle" | "ban";
  title: string;
  children: React.ReactNode;
}) {
  const toneColor = tone === "amber" ? "var(--amber)" : tone === "red" ? "var(--red)" : "var(--faint)";
  return (
    <Frame>
      <div style={{ textAlign: "center", marginBottom: 24 }}>
        <div
          className="empty-icon"
          style={{ background: `${toneColor}18`, color: toneColor, width: 72, height: 72, borderRadius: 20, margin: "0 auto 18px", display: "grid", placeItems: "center" }}
        >
          <Icon name={icon} size={32} />
        </div>
        <h2 style={{ fontSize: 24, marginBottom: 8 }}>{title}</h2>
        <div className="row" style={{ justifyContent: "center", gap: 10 }}>
          <span style={{ fontWeight: 600 }}>{facility.name}</span>
          <Badge value={facility.status} />
        </div>
      </div>
      {children}
    </Frame>
  );
}

export function OnboardingGate() {
  const { user, refreshUser } = useAuth();
  const [appId, setAppId] = useState<number | null>(getStoredApplicationId());
  const facilityId = user?.facility ?? appId;
  const useApplicationEndpoint = !user?.facility && !!appId;

  const query = useQuery({
    queryKey: ["onboarding", facilityId, useApplicationEndpoint],
    queryFn: () =>
      useApplicationEndpoint
        ? FacilitiesApi.application(facilityId as number)
        : FacilitiesApi.get(facilityId as number),
    enabled: !!facilityId,
    refetchInterval: 15_000,
    retry: false,
  });

  // No facility and no stored application → show the apply form.
  if (!facilityId) {
    return (
      <Frame wide>
        <div style={{ marginBottom: 8 }}>
          <div className="eyebrow" style={{ color: "var(--brand)", fontWeight: 700, fontSize: 12, letterSpacing: ".08em", textTransform: "uppercase" }}>
            Facility onboarding
          </div>
          <h2 style={{ fontSize: 26, margin: "4px 0 8px" }}>Register your facility</h2>
          <p className="muted" style={{ maxWidth: "60ch" }}>
            Submit your facility details for central review. Once approved, you'll become the
            facility manager and can set up inventory, staff and vaccination services.
          </p>
        </div>
        <ApplyForm
          onSubmitted={(f) => {
            setStoredApplicationId(f.id);
            setAppId(f.id);
          }}
        />
      </Frame>
    );
  }

  if (query.isLoading) {
    return <Frame><LoadingState label="Loading application status…" /></Frame>;
  }

  const facility = query.data;

  // If the lookup failed, fall back based on the user's own facility status.
  if (!facility) {
    if (user?.facility_status === "SUSPENDED") {
      return (
        <StatusScreen facility={{ name: user.facility_name || "Your facility", status: "SUSPENDED" } as Facility} tone="slate" icon="ban" title="Facility suspended">
          <p className="muted" style={{ textAlign: "center" }}>
            This facility is currently suspended and cannot perform operations. Contact a central
            coordinator or system administrator for assistance.
          </p>
        </StatusScreen>
      );
    }
    clearStoredApplicationId();
    setAppId(null);
    return <Frame><LoadingState label="Resetting…" /></Frame>;
  }

  if (facility.status === "APPROVED") {
    refreshUser();
    return <Frame><LoadingState label="Opening your workspace…" /></Frame>;
  }

  if (facility.status === "PENDING") {
    return (
      <StatusScreen facility={facility} tone="amber" icon="clock" title="Application under review">
        <div className="alert alert-info">
          <Icon name="info" size={17} />
          <span>
            Your application was submitted on <strong>{formatDate(facility.created_at)}</strong>.
            A central coordinator will review it shortly. This page refreshes automatically —
            once approved, you'll be taken straight to your facility workspace.
          </span>
        </div>
        <div className="detail-grid" style={{ marginTop: 8 }}>
          <div className="detail-item"><div className="dt">Type</div><div className="dd">{facility.facility_type_display || facility.facility_type}</div></div>
          <div className="detail-item"><div className="dt">Region</div><div className="dd">{facility.region}</div></div>
          <div className="detail-item"><div className="dt">Cold chain</div><div className="dd">{facility.has_cold_chain ? "Yes" : "No"}</div></div>
          <div className="detail-item"><div className="dt">Vaccination</div><div className="dd">{facility.provides_vaccination_services ? "Yes" : "No"}</div></div>
        </div>
      </StatusScreen>
    );
  }

  if (facility.status === "REJECTED") {
    return (
      <StatusScreen facility={facility} tone="red" icon="x-circle" title="Application not approved">
        {facility.review_note && (
          <div className="alert alert-danger">
            <Icon name="alert" size={17} />
            <div><strong>Reviewer note</strong>{facility.review_note}</div>
          </div>
        )}
        <p className="muted" style={{ textAlign: "center", marginBottom: 20 }}>
          You can review the feedback above and submit a new application.
        </p>
        <div style={{ textAlign: "center" }}>
          <Button
            icon="refresh"
            onClick={() => {
              clearStoredApplicationId();
              setAppId(null);
            }}
          >
            Start a new application
          </Button>
        </div>
      </StatusScreen>
    );
  }

  // SUSPENDED
  return (
    <StatusScreen facility={facility} tone="slate" icon="ban" title="Facility suspended">
      <p className="muted" style={{ textAlign: "center" }}>
        This facility is currently suspended and cannot perform normal operations.
        {facility.review_note && <> Reviewer note: <strong>{facility.review_note}</strong></>}
        {" "}Contact a central coordinator or system administrator for assistance.
      </p>
    </StatusScreen>
  );
}
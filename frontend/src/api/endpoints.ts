import { api } from "./client";
import type {
  AIRecommendation,
  AuditLog,
  CentralDashboard,
  DeliveryCoordination,
  DueResponse,
  Equipment,
  ExpiringResponse,
  Facility,
  FacilityDashboard,
  FacilityMapPoint,
  InventorySummary,
  Paginated,
  Patient,
  Product,
  RegisterPayload,
  StockBatch,
  StockMovement,
  SourcingProposal,
  SupplyGapReport,
  SupplyRequest,
  Tokens,
  TransferRequest,
  UserProfile,
  VaccinationRecord,
  VaccineFollowUp,
  VaccineLite,
  VaccineSchedule,
} from "./types";

type Params = Record<string, string | number | boolean | undefined | null>;

// ---- Auth ----
export const AuthApi = {
  login: (username: string, password: string) =>
    api.post<Tokens>("/auth/token/", { username, password }),
  register: (body: RegisterPayload) => api.post<Tokens>("/auth/register/", body),
  me: () => api.get<UserProfile>("/auth/me/"),
};

// ---- Facilities ----
export const FacilitiesApi = {
  list: (params?: Params) => api.get<Paginated<Facility>>("/facilities/", params),
  get: (id: number) => api.get<Facility>(`/facilities/${id}/`),
  update: (id: number, body: Partial<Facility>) => api.patch<Facility>(`/facilities/${id}/`, body),
  suspend: (id: number, review_note?: string) =>
    api.post<Facility>(`/facilities/${id}/suspend/`, { review_note }),
  map: () => api.get<FacilityMapPoint[]>("/facilities/map/"),
  applications: (params?: Params) => api.get<Paginated<Facility>>("/facilities/applications/", params),
  application: (id: number) => api.get<Facility>(`/facilities/applications/${id}/`),
  apply: (body: Record<string, unknown>) => api.post<Facility>("/facilities/applications/", body),
  approve: (id: number, review_note?: string) =>
    api.post<Facility>(`/facilities/applications/${id}/approve/`, { review_note }),
  reject: (id: number, review_note: string) =>
    api.post<Facility>(`/facilities/applications/${id}/reject/`, { review_note }),
  users: (facilityId: number, params?: Params) =>
    api.get<Paginated<UserProfile>>(`/facilities/${facilityId}/users/`, params),
  createUser: (facilityId: number, body: Record<string, unknown>) =>
    api.post<UserProfile>(`/facilities/${facilityId}/users/`, body),
  deactivateUser: (facilityId: number, userId: number) =>
    api.post<void>(`/facilities/${facilityId}/users/${userId}/deactivate/`, {}),
};

// ---- Products ----
export const ProductsApi = {
  list: (params?: Params) => api.get<Paginated<Product>>("/products/", params),
  get: (id: number) => api.get<Product>(`/products/${id}/`),
  create: (body: Record<string, unknown>) => api.post<Product>("/products/", body),
  update: (id: number, body: Record<string, unknown>) => api.patch<Product>(`/products/${id}/`, body),
  vaccines: () => api.get<VaccineLite[]>("/vaccines/"),
};

// ---- Batches ----
export const BatchesApi = {
  list: (params?: Params) => api.get<Paginated<StockBatch>>("/batches/", params),
  get: (id: number) => api.get<StockBatch>(`/batches/${id}/`),
  update: (id: number, body: { storage_status?: string; source_reference?: string }) =>
    api.patch<StockBatch>(`/batches/${id}/`, body),
};

// ---- Stock operations ----
export const StockApi = {
  receipt: (body: Record<string, unknown>) =>
    api.post<{ batch: StockBatch; movement: StockMovement; replayed: boolean }>("/stock-receipts/", body),
  consumption: (body: Record<string, unknown>) =>
    api.post<{ movement: StockMovement; replayed: boolean }>("/stock-consumption/", body),
  wastage: (body: Record<string, unknown>) =>
    api.post<{ movement: StockMovement; replayed: boolean }>("/stock-wastage/", body),
  adjustment: (body: Record<string, unknown>) =>
    api.post<{ movement: StockMovement; replayed: boolean }>("/stock-adjustments/", body),
  movements: (params?: Params) => api.get<Paginated<StockMovement>>("/stock-movements/", params),
  movement: (id: number) => api.get<StockMovement>(`/stock-movements/${id}/`),
};

// ---- Inventory rollups ----
export const InventoryApi = {
  summary: (params?: Params) => api.get<InventorySummary>("/inventory/summary/", params),
  shortages: (params?: Params) => api.get<InventorySummary>("/inventory/shortages/", params),
  expiring: (params?: Params) => api.get<ExpiringResponse>("/inventory/expiring/", params),
};

// ---- Equipment ----
export const EquipmentApi = {
  list: (params?: Params) => api.get<Paginated<Equipment>>("/equipment/", params),
  create: (body: Record<string, unknown>) => api.post<Equipment>("/equipment/", body),
  update: (id: number, body: Record<string, unknown>) => api.patch<Equipment>(`/equipment/${id}/`, body),
};

// ---- Transfers ----
export const TransfersApi = {
  list: (params?: Params) => api.get<Paginated<TransferRequest>>("/transfers/", params),
  get: (id: number) => api.get<TransferRequest>(`/transfers/${id}/`),
  create: (body: Record<string, unknown>) => api.post<TransferRequest>("/transfers/", body),
  approve: (id: number, quantity_approved?: number) =>
    api.post<TransferRequest>(`/transfers/${id}/approve/`, { quantity_approved }),
  reject: (id: number, rejection_reason: string) =>
    api.post<TransferRequest>(`/transfers/${id}/reject/`, { rejection_reason }),
  dispatch: (id: number, notes?: string) => api.post<TransferRequest>(`/transfers/${id}/dispatch/`, { notes }),
  confirmReceipt: (id: number, body: { quantity_received: number; condition: string; notes?: string }) =>
    api.post<TransferRequest>(`/transfers/${id}/confirm-receipt/`, body),
  cancel: (id: number, reason?: string) => api.post<TransferRequest>(`/transfers/${id}/cancel/`, { reason }),
  deliveryLog: (transferId: number, params?: Params) =>
    api.get<Paginated<DeliveryCoordination>>(`/transfers/${transferId}/delivery-coordination/`, params),
  addDelivery: (transferId: number, body: Record<string, unknown>) =>
    api.post<DeliveryCoordination>(`/transfers/${transferId}/delivery-coordination/`, body),
};

// ---- Supply gaps ----
export const SupplyGapsApi = {
  list: (params?: Params) => api.get<Paginated<SupplyGapReport>>("/central/supply-gaps/", params),
  get: (id: number) => api.get<SupplyGapReport>(`/central/supply-gaps/${id}/`),
  refresh: (params?: Params) =>
    api.post<{ created: number; updated: number; active_count: number; gaps: SupplyGapReport[] }>(
      "/central/supply-gaps/refresh/",
      {},
      params,
    ),
  assign: (id: number, assigned_to: number, note?: string) =>
    api.post<SupplyGapReport>(`/central/supply-gaps/${id}/assign/`, { assigned_to, note }),
  escalate: (id: number, note?: string) =>
    api.post<SupplyGapReport>(`/central/supply-gaps/${id}/escalate/`, { note }),
  resolve: (id: number, resolution_notes: string, final_status: "RESOLVED" | "CLOSED") =>
    api.post<SupplyGapReport>(`/central/supply-gaps/${id}/resolve/`, { resolution_notes, final_status }),
};

// ---- Supply requests & AI sourcing ----
export const SupplyRequestsApi = {
  list: (params?: Params) => api.get<Paginated<SupplyRequest>>("/central/supply-requests/", params),
  cancel: (id: number, reason?: string) =>
    api.post<SupplyRequest>(`/central/supply-requests/${id}/cancel/`, { reason }),
};

export const SourcingApi = {
  proposals: (params?: Params) => api.get<Paginated<SourcingProposal>>("/central/sourcing-proposals/", params),
  plan: (body: { supply_request_ids?: number[]; horizon_days?: number }) =>
    api.post<AIRecommendation>("/ai/plan-transfer-sourcing/", body),
  approve: (id: number, note?: string) =>
    api.post<SourcingProposal>(`/central/sourcing-proposals/${id}/approve/`, { note }),
  reject: (id: number, note: string) =>
    api.post<SourcingProposal>(`/central/sourcing-proposals/${id}/reject/`, { note }),
};

// ---- Vaccinations ----
export const PatientsApi = {
  list: (params?: Params) => api.get<Paginated<Patient>>("/patients/", params),
  get: (id: number) => api.get<Patient>(`/patients/${id}/`),
  create: (body: Record<string, unknown>) => api.post<Patient>("/patients/", body),
  update: (id: number, body: Record<string, unknown>) => api.patch<Patient>(`/patients/${id}/`, body),
};

export const SchedulesApi = {
  list: (params?: Params) => api.get<Paginated<VaccineSchedule>>("/vaccination-schedules/", params),
  create: (body: Record<string, unknown>) => api.post<VaccineSchedule>("/vaccination-schedules/", body),
};

export const VaccinationApi = {
  records: (params?: Params) => api.get<Paginated<VaccinationRecord>>("/vaccination-records/", params),
  record: (id: number) => api.get<VaccinationRecord>(`/vaccination-records/${id}/`),
  createRecord: (body: Record<string, unknown>) =>
    api.post<{ record: VaccinationRecord; next_follow_up: VaccineFollowUp | null }>(
      "/vaccination-records/",
      body,
    ),
  followups: (params?: Params) => api.get<Paginated<VaccineFollowUp>>("/vaccination-followups/", params),
  createFollowup: (body: Record<string, unknown>) =>
    api.post<VaccineFollowUp>("/vaccination-followups/", body),
  contact: (id: number, body: { outcome: string; notes?: string; next_action_date?: string }) =>
    api.post<VaccineFollowUp>(`/vaccination-followups/${id}/contact/`, body),
  markReview: (id: number, reason: string) =>
    api.post<VaccineFollowUp>(`/vaccination-followups/${id}/mark-review-required/`, { reason }),
  cancelFollowup: (id: number, reason?: string) =>
    api.post<VaccineFollowUp>(`/vaccination-followups/${id}/cancel/`, { reason }),
  due: () => api.get<DueResponse>("/vaccinations/due/"),
  overdue: () => api.get<DueResponse>("/vaccinations/overdue/"),
};

// ---- AI ----
export const AIApi = {
  analyzeInventory: (body: { facility?: number; horizon_days?: number }) =>
    api.post<AIRecommendation>("/ai/analyze-inventory/", body),
  prioritizeGaps: (body: { horizon_days?: number }) =>
    api.post<AIRecommendation>("/ai/prioritize-supply-gaps/", body),
  summarizeVaccination: (body: { facility: number; horizon_days?: number }) =>
    api.post<AIRecommendation>("/ai/summarize-vaccination-demand/", body),
  list: (params?: Params) => api.get<Paginated<AIRecommendation>>("/ai/recommendations/", params),
  get: (id: number) => api.get<AIRecommendation>(`/ai/recommendations/${id}/`),
  planGapSourcing: (body: { gap_ids?: number[]; horizon_days?: number }) =>
    api.post<AIRecommendation>("/ai/plan-gap-sourcing/", body),
  approve: (id: number, note?: string) =>
    api.post<AIRecommendation>(`/ai/recommendations/${id}/approve/`, { note }),
  reject: (id: number, note: string) =>
    api.post<AIRecommendation>(`/ai/recommendations/${id}/reject/`, { note }),
};

// ---- Dashboards ----
export const DashboardApi = {
  facility: (params?: Params) => api.get<FacilityDashboard>("/dashboard/facility-summary/", params),
  central: () => api.get<CentralDashboard>("/dashboard/central-summary/"),
};

// ---- Audit ----
export const AuditApi = {
  list: (params?: Params) => api.get<Paginated<AuditLog>>("/audit/logs/", params),
};
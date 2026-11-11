// Types mirroring the MedBridge backend API contract (frontend.txt).
// Decimal fields are serialized as strings by the backend.

export type Role =
  | "SYSTEM_ADMIN"
  | "CENTRAL_COORDINATOR"
  | "FACILITY_MANAGER"
  | "PHARMACIST"
  | "INVENTORY_STAFF"
  | "PHARMACY_STAFF"
  | "HEALTH_WORKER";

export type FacilityType = "CLINIC" | "HOSPITAL" | "HEALTH_CENTER" | "PHARMACY" | "OTHER";
export type FacilityStatus = "PENDING" | "APPROVED" | "REJECTED" | "SUSPENDED";
export type ProductCategory = "MEDICINE" | "VACCINE";
export type StorageStatus = "OK" | "QUARANTINED" | "TEMPERATURE_EXCURSION" | "DAMAGED" | "EXPIRED";
export type MovementType =
  | "RECEIPT"
  | "CONSUMPTION"
  | "VACCINATION_ADMINISTRATION"
  | "TRANSFER_OUT"
  | "TRANSFER_IN"
  | "WASTAGE"
  | "ADJUSTMENT"
  | "RETURN";
export type MovementDirection = "IN" | "OUT";
export type TransferStatus =
  | "DRAFT"
  | "REQUESTED"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "DISPATCHED"
  | "IN_TRANSIT"
  | "RECEIVED"
  | "CANCELLED"
  | "FAILED";
export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type DeliveryPayer = "CENTRAL" | "SENDER" | "RECEIVER" | "PARTNER" | "UNDECIDED";
export type DeliveryPhoneStatus = "PENDING" | "CONFIRMED" | "CANCELLED";
export type DeliveryStatus =
  | "NOT_ARRANGED"
  | "ARRANGED_BY_PHONE"
  | "DISPATCHED"
  | "RECEIVED"
  | "FAILED"
  | "DISCREPANCY";
export type GapStatus =
  | "OPEN"
  | "UNDER_REVIEW"
  | "ASSIGNED"
  | "ACTION_PLANNED"
  | "ESCALATED"
  | "RESOLVED"
  | "CLOSED";
export type EquipmentCondition = "OPERATIONAL" | "NEEDS_MAINTENANCE" | "OUT_OF_SERVICE";
export type Sex = "MALE" | "FEMALE" | "OTHER" | "UNKNOWN";
export type FollowUpStatus =
  | "UPCOMING"
  | "DUE"
  | "OVERDUE"
  | "COMPLETED"
  | "CONTACT_ATTEMPTED"
  | "REVIEW_REQUIRED"
  | "CANCELLED";
export type ContactOutcome = "REACHED" | "NO_ANSWER" | "RESCHEDULED" | "REFERRED_FOR_REVIEW";
export type AIAnalysisType =
  | "INVENTORY_ANALYSIS"
  | "SUPPLY_GAP_PRIORITIZATION"
  | "VACCINATION_DEMAND_SUMMARY"
  | "TRANSFER_SOURCING";
export type AIStatus = "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "FAILED" | "INVALID";

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  phone: string;
  facility: number | null;
  facility_name?: string | null;
  facility_status?: FacilityStatus | null;
  is_active: boolean;
  date_joined: string;
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
}

export interface Facility {
  id: number;
  name: string;
  facility_type: FacilityType;
  facility_type_display?: string;
  registration_number: string | null;
  region: string;
  zone: string;
  woreda: string;
  kebele: string;
  town: string;
  address: string;
  landmark: string;
  latitude: string | null;
  longitude: string | null;
  contact_phone: string;
  contact_email: string;
  storage_capacity_notes: string;
  has_cold_chain: boolean;
  cold_chain_notes: string;
  provides_vaccination_services: boolean;
  status: FacilityStatus;
  status_display?: string;
  is_active: boolean;
  submitted_by: number | null;
  submitted_by_username?: string | null;
  reviewed_by: number | null;
  reviewed_by_username?: string | null;
  reviewed_at: string | null;
  review_note: string;
  created_at: string;
  updated_at: string;
}

export interface FacilityMapPoint {
  id: number;
  name: string;
  facility_type: FacilityType;
  region: string;
  latitude: string;
  longitude: string;
}

export interface Product {
  id: number;
  name: string;
  category: ProductCategory;
  category_display?: string;
  generic_name: string;
  strength: string;
  dosage_form: string;
  unit_of_measure: string;
  description: string;
  requires_cold_chain: boolean;
  storage_min_temperature: string | null;
  storage_max_temperature: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VaccineLite {
  id: number;
  name: string;
  generic_name: string;
  unit_of_measure: string;
  requires_cold_chain: boolean;
  description: string;
}

export interface StockBatch {
  id: number;
  facility: number;
  facility_name: string;
  product: number;
  product_name: string;
  product_category: ProductCategory;
  batch_number: string;
  expiry_date: string;
  quantity_received: number;
  quantity_available: number;
  quantity_reserved: number;
  storage_status: StorageStatus;
  storage_status_display?: string;
  received_at: string;
  source_reference: string;
  is_expired: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface StockMovement {
  id: number;
  batch: number;
  batch_number: string;
  product_name: string;
  product_category: ProductCategory;
  facility_id: number;
  facility_name: string;
  movement_type: MovementType;
  movement_type_display?: string;
  direction: MovementDirection;
  quantity: number;
  reference_type: string;
  reference_id: string;
  reason: string;
  performed_by: number | null;
  performed_by_username: string;
  occurred_at: string;
  created_at: string;
  idempotency_key: string | null;
}

export interface InventoryItemSummary {
  product_id: number;
  product_name: string;
  category: ProductCategory;
  unit_of_measure: string;
  usable_stock: number;
  reserved_stock: number;
  incoming_stock: number;
  projected_demand: number | null;
  projected_gap: number | null;
  days_of_stock: number | null;
  estimated_daily_usage: number | null;
  follow_up_demand: number;
  near_expiry_quantity: number;
  batch_count: number;
}

export interface InventorySummary {
  facility_id: number;
  facility_name: string;
  as_of: string;
  horizon_days: number;
  near_expiry_days: number;
  usage_window_days: number;
  items: InventoryItemSummary[];
}

export interface ExpiringBatch {
  batch_id: number;
  batch_number: string;
  product_id: number;
  product_name: string;
  category: ProductCategory;
  quantity_available: number;
  expiry_date: string;
  days_until_expiry: number;
  storage_status: StorageStatus;
}

export interface ExpiringResponse {
  facility_id: number;
  facility_name: string;
  as_of: string;
  near_expiry_days: number;
  batches: ExpiringBatch[];
}

export interface Equipment {
  id: number;
  facility: number;
  facility_name: string;
  name: string;
  category: string;
  asset_identifier: string;
  quantity: number;
  condition: EquipmentCondition;
  condition_display?: string;
  notes: string;
  last_checked_at: string | null;
  created_by: number | null;
  created_by_username: string;
  created_at: string;
  updated_at: string;
}

export interface TransferRequest {
  id: number;
  source_facility: number;
  source_facility_name: string;
  destination_facility: number;
  destination_facility_name: string;
  product: number;
  product_name: string;
  source_batch: number | null;
  source_batch_number: string;
  source_batch_expiry: string | null;
  quantity_requested: number;
  quantity_approved: number | null;
  quantity_received: number | null;
  status: TransferStatus;
  status_display?: string;
  priority: Priority;
  priority_display?: string;
  requested_by: number | null;
  requested_by_username: string;
  approved_by: number | null;
  approved_by_username: string | null;
  approved_at: string | null;
  rejection_reason: string;
  received_by: number | null;
  received_at: string | null;
  condition_on_receipt: string;
  expected_dispatch_at: string | null;
  expected_arrival_at: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface DeliveryCoordination {
  id: number;
  transfer_request: number;
  transfer_request_id: number;
  transport_method: string;
  transport_provider: string;
  contact_person_name: string;
  contact_phone: string;
  transport_payer: DeliveryPayer;
  estimated_cost: string | null;
  currency: string;
  agreed_pickup_at: string | null;
  expected_arrival_at: string | null;
  phone_coordination_status: DeliveryPhoneStatus;
  delivery_status: DeliveryStatus;
  coordinator: number | null;
  coordinator_username: string;
  last_contacted_at: string | null;
  receipt_confirmed_by: number | null;
  receipt_confirmed_at: string | null;
  quantity_received: number | null;
  condition_on_receipt: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface SupplyRequest {
  id: number;
  facility: number;
  facility_name: string;
  product: number;
  product_name: string;
  product_category: string;
  unit_of_measure: string;
  quantity: number;
  reason: string;
  source_recommendation: number | null;
  status: "OPEN" | "PLANNED" | "FULFILLED" | "CANCELLED";
  status_display: string;
  requested_by: number | null;
  requested_by_username: string | null;
  open_proposals_count: number;
  created_at: string;
  updated_at: string;
}

export interface SourcingProposal {
  id: number;
  request: number;
  recommendation: number | null;
  source_facility: number;
  source_facility_name: string;
  product: number;
  product_name: string;
  quantity: number;
  reason: string;
  reason_amharic?: string;
  status: "PROPOSED" | "APPROVED" | "REJECTED";
  status_display: string;
  requesting_facility_name: string;
  transfer: number | null;
  transfer_id: number | null;
  transfer_status: string | null;
  review_note: string;
  reviewed_by: number | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplyGapReport {
  id: number;
  facility: number;
  facility_name: string;
  product: number;
  product_name: string;
  product_category: ProductCategory;
  reporting_horizon_start: string;
  reporting_horizon_end: string;
  projected_demand: number;
  usable_stock: number;
  reliable_incoming_quantity: number;
  uncovered_quantity: number;
  priority: Priority;
  priority_display?: string;
  reason_summary: string;
  status: GapStatus;
  status_display?: string;
  assigned_to: number | null;
  assigned_to_username: string | null;
  resolution_notes: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  active_request?: {
    id: number;
    status: string;
    status_display: string;
    quantity: number;
    proposal_status: string | null;
    transfer_id: number | null;
  } | null;
}

export interface Patient {
  id: number;
  facility: number;
  facility_name: string;
  patient_number: string;
  full_name: string;
  date_of_birth: string;
  sex: Sex;
  sex_display?: string;
  guardian_name: string;
  guardian_phone: string;
  patient_phone: string;
  address_area: string;
  consent_given: boolean;
  consent_date: string | null;
  active: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface VaccineSchedule {
  id: number;
  vaccine_product: number;
  vaccine_product_name: string;
  dose_number: number;
  recommended_age_days: number | null;
  recommended_age_label: string;
  minimum_interval_days: number | null;
  effective_from: string;
  effective_to: string | null;
  source_name: string;
  source_version: string;
  approved_by: number | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VaccinationRecord {
  id: number;
  patient: number;
  patient_number: string;
  patient_name: string;
  vaccine_product: number;
  vaccine_product_name: string;
  schedule: number | null;
  schedule_id: number | null;
  dose_number: number;
  administered_at: string;
  facility: number;
  facility_name: string;
  batch: number;
  batch_number: string;
  recorded_by: number | null;
  recorded_by_username: string;
  notes: string;
  created_at: string;
}

export interface VaccineFollowUp {
  id: number;
  patient: number;
  patient_number: string;
  patient_name: string;
  vaccine_product: number;
  vaccine_product_name: string;
  dose_number: number;
  due_date: string;
  status: FollowUpStatus;
  status_display?: string;
  effective_status: FollowUpStatus;
  assigned_to: number | null;
  assigned_to_username: string | null;
  last_contacted_at: string | null;
  contact_outcome: string;
  contact_outcome_display?: string;
  next_action_date: string | null;
  review_reason: string;
  created_at: string;
  updated_at: string;
}

export interface DueResponse {
  as_of: string;
  window_days?: number;
  count: number;
  follow_ups: VaccineFollowUp[];
}

export interface AIRisk {
  facility_id: number;
  facility_name?: string;
  product_id: number;
  priority: Priority;
  reason: string;
  reason_amharic?: string;
}

export interface AITransferRecommendation {
  source_facility_id: number;
  source_facility_name?: string;
  destination_facility_id: number;
  destination_facility_name?: string;
  product_id: number;
  product_name?: string;
  quantity: number;
  reason: string;
  reason_amharic?: string;
}

export interface AIRankedGap {
  gap_id: number;
  priority: Priority;
  rank: number;
  reason: string;
  reason_amharic?: string;
}

export interface AIProductDemand {
  product_id: number;
  product_name: string;
  open_follow_ups: number;
  due_next_7_days: number;
  due_next_30_days: number;
  usable_stock: number;
  projected_gap: number | null;
  comment: string;
  comment_amharic?: string;
}

export interface AISourcingProposal {
  request_id: number;
  requesting_facility_id: number;
  requesting_facility_name?: string;
  source_facility_id: number;
  source_facility_name?: string;
  product_id: number;
  product_name?: string;
  quantity: number;
  reason: string;
  reason_amharic?: string;
}

export interface AIValidatedOutput {
  summary?: string;
  summary_amharic?: string;
  risks?: AIRisk[];
  transfer_recommendations?: AITransferRecommendation[];
  unresolved_gaps?: { facility_id: number; product_id: number; quantity: number }[];
  ranked_gaps?: AIRankedGap[];
  by_product?: AIProductDemand[];
  proposals?: AISourcingProposal[];
  priorities?: string[];
  priorities_amharic?: string[];
  missing_information?: string[];
  missing_information_amharic?: string[];
  [key: string]: unknown;
}

export interface AIRecommendation {
  id: number;
  analysis_type: AIAnalysisType;
  analysis_type_display?: string;
  status: AIStatus;
  status_display?: string;
  scope_facility: number | null;
  scope_facility_name: string | null;
  requested_by: number | null;
  requested_by_username: string;
  model_name: string;
  summary: string;
  validated_output: AIValidatedOutput | null;
  validation_errors: Record<string, unknown>[];
  error: string;
  reviewed_by: number | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
  review_note: string;
  input_snapshot?: Record<string, unknown>;
  raw_output?: Record<string, unknown>;
  supply_requests_created?: number | null;
  proposals_created?: number | null;
  created_at: string;
  updated_at: string;
}

export interface AIQueueItem {
  id: number;
  analysis_type: AIAnalysisType;
  scope_facility_id: number | null;
  scope_facility_name: string | null;
  summary: string;
  created_at: string;
  validation_error_count: number;
}

export interface AuditLog {
  id: number;
  actor: number | null;
  actor_username: string;
  actor_role: Role;
  actor_facility_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface FacilityDashboard {
  facility: Facility;
  as_of: string;
  inventory: {
    total_batches: number;
    usable_units: number;
    products_with_gap: number;
    critical_shortages: number;
  };
  shortages: InventoryItemSummary[];
  near_expiry: ExpiringBatch[];
  transfers: { incoming: TransferRequest[]; outgoing: TransferRequest[] };
  vaccinations: { due_in_7_days: number; overdue: number };
  equipment: { total: number; out_of_service: number; needs_maintenance: number };
  recent_movements: StockMovement[];
  recent_audit: AuditLog[];
  data_freshness: { last_stock_movement_at: string | null; last_audit_at: string | null };
}

export interface CentralDashboard {
  as_of: string;
  facilities: { pending_applications: number; approved: number; suspended: number };
  stock: { medicine_units: number; vaccine_units: number };
  top_gaps: {
    id: number;
    facility_id: number;
    facility_name: string;
    product_id: number;
    product_name: string;
    priority: Priority;
    uncovered_quantity: number;
    status: GapStatus;
    reporting_horizon_end: string;
  }[];
  near_expiry_redistribution: {
    batch_id: number;
    facility_id: number;
    facility_name: string;
    product_id: number;
    product_name: string;
    batch_number: string;
    quantity_available: number;
    expiry_date: string;
    days_until_expiry: number;
  }[];
  transfers: {
    requested: number;
    approved: number;
    dispatched: number;
    in_transit: number;
    received: number;
    recent_7d: number;
  };
  supply_gaps: {
    open: number;
    under_review: number;
    assigned: number;
    action_planned: number;
    escalated: number;
    resolved: number;
    closed: number;
    critical_active: number;
    high_active: number;
  };
  deliveries: {
    arranged_by_phone: number;
    dispatched: number;
    received: number;
    discrepancy: number;
    failed: number;
  };
  vaccinations: { due_7d: number; overdue: number };
  ai_recommendations: {
    pending_review: number;
    failed_last_7_days: number;
    queue: AIQueueItem[];
  };
}

// Normalized API error
export interface ApiError {
  status: number;
  detail: string;
  code?: string;
  fieldErrors?: Record<string, string[]>;
}
/**
 * Central type definitions for the HUMS platform.
 * All types mirror the backend API response schemas.
 */

// ── Enumerations ──────────────────────────────────────────────────────────────

export type AssetType =
  | 'AIRCRAFT'
  | 'GROUND_VEHICLE'
  | 'MARITIME'
  | 'ROTARY_WING'
  | 'FIXED_WING'
  | 'SUPPORT_EQUIPMENT';

export type ReadinessStatus =
  | 'READY'
  | 'READY_WITH_CAUTION'
  | 'MAINTENANCE_REQUIRED'
  | 'NOT_READY'
  | 'INSUFFICIENT_DATA';

export type RiskCategory = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type AnomalySeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type MaintenancePriority = 'IMMEDIATE' | 'HIGH' | 'PLANNED' | 'MONITOR';

export type ReviewStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'MODIFIED';

export type DataQualityLevel = 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'INSUFFICIENT';

// ── Entity types ──────────────────────────────────────────────────────────────

export interface Asset {
  id: string;
  asset_id: string;
  name: string;
  asset_type: AssetType;
  fleet?: string;
  location?: string;
  total_operating_hours: number;
  total_cycles: number;
  is_active: boolean;
}

export interface Component {
  id: string;
  asset_id: string;
  component_id: string;
  name: string;
  component_type: string;
  criticality: string;
  design_life_hours?: number;
  current_operating_hours: number;
  current_cycles: number;
}

export interface SensorReading {
  id: string;
  asset_id: string;
  component_id?: string;
  timestamp: string;
  sensor_type: string;
  sensor_value: number;
  unit?: string;
  quality_flag?: string;
}

export interface AnomalyEvent {
  id: string;
  asset_id: string;
  component_id?: string;
  sensor_type: string;
  detected_at: string;
  anomaly_type: string;
  severity: AnomalySeverity;
  anomaly_score: number;
  sensor_value?: number;
  baseline_value?: number;
  deviation_pct?: number;
  evidence?: Record<string, unknown>;
}

export interface Prediction {
  id: string;
  asset_id: string;
  component_id: string;
  predicted_at: string;
  prediction_horizon_days: number;
  risk_score: number;
  risk_category: RiskCategory;
  risk_factors?: string[];
  uncertainty?: number;
  data_sufficiency?: number;
  model_version?: string;
}

export interface ReadinessAssessment {
  id: string;
  asset_id: string;
  assessed_at: string;
  status: ReadinessStatus;
  overall_health_score?: number;
  primary_evidence?: string[];
  data_quality_score?: number;
  explanation?: string;
}

export interface MaintenanceRecommendation {
  id: string;
  asset_id: string;
  component_id: string;
  generated_at: string;
  priority: MaintenancePriority;
  issue_summary: string;
  evidence?: string[];
  recommended_action: string;
  urgency_days?: number;
  risk_score?: number;
  data_confidence?: number;
  human_review_required: boolean;
  review_status: ReviewStatus;
}

export interface DataQualityReport {
  id: string;
  asset_id: string;
  report_date: string;
  completeness_score: number;
  validity_score: number;
  consistency_score: number;
  timeliness_score: number;
  duplicate_rate: number;
  missing_value_rate: number;
  outlier_rate: number;
  overall_score: number;
  quality_level: DataQualityLevel;
  total_records: number;
}

// ── API response wrappers ─────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  total: number;
  items: T[];
}

export interface DashboardSummary {
  total_assets: number;
  ready: number;
  ready_with_caution: number;
  maintenance_required: number;
  not_ready: number;
  insufficient_data: number;
  high_risk_components: number;
  open_recommendations: number;
  data_quality_score: number;
  last_updated?: string;
}

export interface CopilotResponse {
  question: string;
  answer: string;
  source: 'gemini' | 'deterministic' | 'stub';
  evidence: string[];
}

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Dashboard ──────────────────────────────────────────────────────────────────
export const getDashboardSummary = () => api.get('/dashboard/summary').then(r => r.data);
export const getFleetHealthMatrix = () => api.get('/dashboard/fleet-health-matrix').then(r => r.data);
export const getSensorHeatmap = (days = 30) => api.get(`/dashboard/sensor-heatmap?days=${days}`).then(r => r.data);

// ── Assets ─────────────────────────────────────────────────────────────────────
export const listAssets = (params?: { skip?: number; limit?: number; asset_type?: string; fleet?: string }) =>
  api.get('/assets', { params }).then(r => r.data);
export const getAsset = (id: string) => api.get(`/assets/${id}`).then(r => r.data);
export const getAssetSensorHistory = (id: string, params?: { sensor_type?: string; component_id?: string; days?: number }) =>
  api.get(`/assets/${id}/sensor-history`, { params }).then(r => r.data);

// ── Anomalies ──────────────────────────────────────────────────────────────────
export const listAnomalies = (params?: { skip?: number; limit?: number; severity?: string; asset_id?: string; days?: number }) =>
  api.get('/anomalies', { params }).then(r => r.data);
export const getAnomalyTimeline = (days = 30) => api.get(`/anomalies/timeline?days=${days}`).then(r => r.data);
export const acknowledgeAnomaly = (id: string) => api.patch(`/anomalies/${id}/acknowledge`).then(r => r.data);

// ── Predictions ─────────────────────────────────────────────────────────────────
export const listPredictions = (params?: { skip?: number; limit?: number; risk_category?: string; asset_id?: string }) =>
  api.get('/predictions', { params }).then(r => r.data);
export const getFailureRiskHorizon = (top_n = 20) => api.get(`/predictions/failure-risk-horizon?top_n=${top_n}`).then(r => r.data);
export const explainPrediction = (id: string) => api.get(`/predictions/${id}/explain`).then(r => r.data);

// ── Readiness ──────────────────────────────────────────────────────────────────
export const listReadiness = (params?: { skip?: number; limit?: number; status?: string }) =>
  api.get('/readiness', { params }).then(r => r.data);
export const getAssetReadiness = (asset_id: string) => api.get(`/readiness/asset/${asset_id}`).then(r => r.data);

// ── Maintenance ─────────────────────────────────────────────────────────────────
export const listMaintenance = (params?: { skip?: number; limit?: number }) =>
  api.get('/maintenance', { params }).then(r => r.data);
export const updateMaintenanceReview = (id: string, data: { review_status: string; reviewer_notes?: string; reviewed_by?: string }) =>
  api.patch(`/maintenance/${id}/review`, data).then(r => r.data);

// ── Data Quality ───────────────────────────────────────────────────────────────
export const listDataQuality = (params?: { skip?: number; limit?: number }) =>
  api.get('/data-quality', { params }).then(r => r.data);
export const getAssetDataQuality = (asset_id: string) => api.get(`/data-quality/asset/${asset_id}`).then(r => r.data);
export const getFleetDataQualitySummary = () => api.get('/data-quality/fleet-summary').then(r => r.data);

// ── Pipeline ──────────────────────────────────────────────────────────────────
export const triggerPipeline = (asset_id?: string) => api.post('/pipeline/run', null, { params: { asset_id } }).then(r => r.data);
export const runPipelineSync = (asset_id?: string, limit = 5) => api.post('/pipeline/run-sync', null, { params: { asset_id, limit } }).then(r => r.data);

// ── Copilot ───────────────────────────────────────────────────────────────────
export const copilotQuery = (query: string, asset_id?: string) =>
  api.post('/copilot/query', { query, asset_id }).then(r => r.data);
export const getCopilotHealth = () => api.get('/copilot/health').then(r => r.data);

// ── Ingestion ─────────────────────────────────────────────────────────────────
export const uploadSensorCSV = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/ingestion/sensors', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};
export const uploadMaintenanceCSV = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/ingestion/maintenance', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};

export default api;

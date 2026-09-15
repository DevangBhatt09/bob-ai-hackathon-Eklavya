/**
 * Theme tokens and utilities.
 *
 * Centralized semantic color tokens used by all charts and UI components.
 * Components consume these tokens — never hardcode colors.
 *
 * Both light and dark theme values are defined here so charts can adapt
 * regardless of which Tailwind class is active on <html>.
 */

export type Theme = 'light' | 'dark';

// ── Semantic color tokens ─────────────────────────────────────────────────────

export interface ThemeTokens {
  background: string;
  surface: string;
  surfaceSecondary: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  gridLine: string;
  tooltipBg: string;
  tooltipText: string;
  // Status colors
  ready: string;
  readyBg: string;
  caution: string;
  cautionBg: string;
  maintenanceRequired: string;
  maintenanceRequiredBg: string;
  notReady: string;
  notReadyBg: string;
  insufficientData: string;
  // Risk colors
  riskLow: string;
  riskMedium: string;
  riskHigh: string;
  riskCritical: string;
  // Anomaly severity
  anomalyLow: string;
  anomalyMedium: string;
  anomalyHigh: string;
  anomalyCritical: string;
}

export const LIGHT_TOKENS: ThemeTokens = {
  background: '#f8fafc',
  surface: '#ffffff',
  surfaceSecondary: '#f1f5f9',
  textPrimary: '#1e293b',
  textSecondary: '#64748b',
  border: '#e2e8f0',
  gridLine: '#e2e8f0',
  tooltipBg: '#1e293b',
  tooltipText: '#f8fafc',
  ready: '#16a34a',
  readyBg: '#dcfce7',
  caution: '#d97706',
  cautionBg: '#fef3c7',
  maintenanceRequired: '#dc2626',
  maintenanceRequiredBg: '#fee2e2',
  notReady: '#7c3aed',
  notReadyBg: '#ede9fe',
  insufficientData: '#94a3b8',
  riskLow: '#16a34a',
  riskMedium: '#d97706',
  riskHigh: '#dc2626',
  riskCritical: '#7c3aed',
  anomalyLow: '#3b82f6',
  anomalyMedium: '#d97706',
  anomalyHigh: '#dc2626',
  anomalyCritical: '#7c3aed',
};

export const DARK_TOKENS: ThemeTokens = {
  background: '#0f172a',
  surface: '#1e293b',
  surfaceSecondary: '#283548',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  border: '#334155',
  gridLine: '#334155',
  tooltipBg: '#0f172a',
  tooltipText: '#f1f5f9',
  ready: '#22c55e',
  readyBg: '#14532d',
  caution: '#f59e0b',
  cautionBg: '#78350f',
  maintenanceRequired: '#f87171',
  maintenanceRequiredBg: '#7f1d1d',
  notReady: '#a78bfa',
  notReadyBg: '#3b0764',
  insufficientData: '#64748b',
  riskLow: '#22c55e',
  riskMedium: '#f59e0b',
  riskHigh: '#f87171',
  riskCritical: '#a78bfa',
  anomalyLow: '#60a5fa',
  anomalyMedium: '#f59e0b',
  anomalyHigh: '#f87171',
  anomalyCritical: '#a78bfa',
};

// ── Helper utilities ──────────────────────────────────────────────────────────

import type { ReadinessStatus, RiskCategory, AnomalySeverity, DataQualityLevel } from '../types';

export function getReadinessColor(status: ReadinessStatus, tokens: ThemeTokens): string {
  switch (status) {
    case 'READY': return tokens.ready;
    case 'READY_WITH_CAUTION': return tokens.caution;
    case 'MAINTENANCE_REQUIRED': return tokens.maintenanceRequired;
    case 'NOT_READY': return tokens.notReady;
    case 'INSUFFICIENT_DATA': return tokens.insufficientData;
    default: return tokens.insufficientData;
  }
}

export function getReadinessBg(status: ReadinessStatus, tokens: ThemeTokens): string {
  switch (status) {
    case 'READY': return tokens.readyBg;
    case 'READY_WITH_CAUTION': return tokens.cautionBg;
    case 'MAINTENANCE_REQUIRED': return tokens.maintenanceRequiredBg;
    case 'NOT_READY': return tokens.notReadyBg;
    case 'INSUFFICIENT_DATA': return tokens.surfaceSecondary;
    default: return tokens.surfaceSecondary;
  }
}

export function getRiskColor(risk: RiskCategory, tokens: ThemeTokens): string {
  switch (risk) {
    case 'LOW': return tokens.riskLow;
    case 'MEDIUM': return tokens.riskMedium;
    case 'HIGH': return tokens.riskHigh;
    case 'CRITICAL': return tokens.riskCritical;
    default: return tokens.insufficientData;
  }
}

export function getAnomalyColor(severity: AnomalySeverity, tokens: ThemeTokens): string {
  switch (severity) {
    case 'LOW': return tokens.anomalyLow;
    case 'MEDIUM': return tokens.anomalyMedium;
    case 'HIGH': return tokens.anomalyHigh;
    case 'CRITICAL': return tokens.anomalyCritical;
    default: return tokens.insufficientData;
  }
}

export function getDataQualityColor(level: DataQualityLevel, tokens: ThemeTokens): string {
  switch (level) {
    case 'EXCELLENT': return tokens.riskLow;
    case 'GOOD': return tokens.ready;
    case 'FAIR': return tokens.caution;
    case 'POOR': return tokens.riskHigh;
    case 'INSUFFICIENT': return tokens.insufficientData;
    default: return tokens.insufficientData;
  }
}

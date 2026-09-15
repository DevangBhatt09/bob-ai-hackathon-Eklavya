"""
Phase 8 — Risk/Failure Prediction Engine
==========================================
Three-layer prediction architecture:

  Layer 1 — Rule-Based Heuristics
    Fast, explainable rules derived from domain knowledge:
    - Design life utilisation (hours/cycles fraction)
    - Time since last maintenance vs recommended interval
    - Recent anomaly count and severity
    - Sensor trend slope (positive slope = degrading)
    - Data quality gate (insufficient data → uncertain, never healthy)

  Layer 2 — Statistical Trends
    Extrapolates current sensor trends using linear regression:
    - Slope-based time-to-threshold for critical sensors
    - Degradation rate from baseline deviation
    - Maintenance interval overrun fraction

  Layer 3 — Ensemble Aggregation
    Combines Layer 1 and Layer 2 scores with confidence weights:
    - More weight to rules when data is limited
    - More weight to statistical trends when data is rich
    - Always outputs: risk_score (0.0–1.0), risk_category, uncertainty

Data-leakage rule:
  All predictions use ONLY historical data up to `as_of`.

Output:
  Prediction record persisted to PostgreSQL with full audit trail.
  risk_factors list explains which factors drove the score.

Safety note:
  This engine produces MAINTENANCE readiness assessments only.
  It does NOT produce tactical readiness, mission readiness, or
  combat capability assessments.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.analytics.feature_engineering import compute_component_features
from app.models.models import (
    AnomalyEvent,
    AnomalySeverity,
    Asset,
    Component,
    DataQualityLevel,
    Prediction,
    RiskCategory,
)

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────

# Design life utilisation thresholds (fraction of design life consumed)
DL_RISK_THRESHOLDS = {
    RiskCategory.CRITICAL: 0.90,
    RiskCategory.HIGH: 0.75,
    RiskCategory.MEDIUM: 0.55,
    RiskCategory.LOW: 0.0,
}

# Max recommended maintenance interval days (generic fallback)
DEFAULT_MAINTENANCE_INTERVAL_DAYS = 90.0

# Anomaly counts that push risk up
ANOMALY_RISK_MAP = {
    AnomalySeverity.CRITICAL: 0.35,
    AnomalySeverity.HIGH: 0.20,
    AnomalySeverity.MEDIUM: 0.10,
    AnomalySeverity.LOW: 0.03,
}

MODEL_VERSION = "prediction_v1"


# ── Risk score → category ────────────────────────────────────────────────────

def _score_to_category(score: float) -> RiskCategory:
    """Map a continuous 0–1 risk score to a discrete category."""
    if score >= 0.75:
        return RiskCategory.CRITICAL
    elif score >= 0.55:
        return RiskCategory.HIGH
    elif score >= 0.30:
        return RiskCategory.MEDIUM
    else:
        return RiskCategory.LOW


# ── Layer 1: Rule-based heuristics ────────────────────────────────────────────

def _layer1_rules(
    component: Component,
    features: dict[str, Any],
    anomaly_counts: dict[str, int],
    as_of: datetime,
) -> tuple[float, list[dict]]:
    """
    Compute rule-based risk score from domain heuristics.
    Returns (score 0–1, list of contributing risk factors).
    """
    score = 0.0
    factors: list[dict] = []

    # ── R1: Design life utilisation ─────────────────────────────────────────
    dl_hours = component.design_life_hours
    cur_hours = component.current_operating_hours or 0.0
    if dl_hours and dl_hours > 0:
        util_frac = cur_hours / dl_hours
        util_contribution = min(0.50, util_frac * 0.50)
        score += util_contribution
        if util_frac >= DL_RISK_THRESHOLDS[RiskCategory.CRITICAL]:
            factors.append({
                "factor": "design_life_utilisation",
                "value": float(util_frac),
                "threshold": DL_RISK_THRESHOLDS[RiskCategory.CRITICAL],
                "contribution": float(util_contribution),
                "severity": "CRITICAL",
                "description": f"Component at {util_frac:.0%} of design life ({cur_hours:.0f}/{dl_hours:.0f} hours)",
            })
        elif util_frac >= DL_RISK_THRESHOLDS[RiskCategory.HIGH]:
            factors.append({
                "factor": "design_life_utilisation",
                "value": float(util_frac),
                "threshold": DL_RISK_THRESHOLDS[RiskCategory.HIGH],
                "contribution": float(util_contribution),
                "severity": "HIGH",
                "description": f"Component at {util_frac:.0%} of design life",
            })
        elif util_frac >= DL_RISK_THRESHOLDS[RiskCategory.MEDIUM]:
            factors.append({
                "factor": "design_life_utilisation",
                "value": float(util_frac),
                "threshold": DL_RISK_THRESHOLDS[RiskCategory.MEDIUM],
                "contribution": float(util_contribution),
                "severity": "MEDIUM",
                "description": f"Component at {util_frac:.0%} of design life",
            })

    # ── R2: Maintenance interval overrun ────────────────────────────────────
    days_since = features.get("days_since_maintenance")
    if days_since is not None:
        overrun_frac = days_since / DEFAULT_MAINTENANCE_INTERVAL_DAYS
        overrun_contribution = min(0.25, overrun_frac * 0.25)
        score += overrun_contribution
        if overrun_frac >= 1.5:
            factors.append({
                "factor": "maintenance_interval_overrun",
                "value": float(days_since),
                "threshold": DEFAULT_MAINTENANCE_INTERVAL_DAYS * 1.5,
                "contribution": float(overrun_contribution),
                "severity": "HIGH",
                "description": f"No maintenance in {days_since:.0f} days (overdue by {days_since - DEFAULT_MAINTENANCE_INTERVAL_DAYS:.0f} days)",
            })
        elif overrun_frac >= 1.0:
            factors.append({
                "factor": "maintenance_interval_overrun",
                "value": float(days_since),
                "threshold": DEFAULT_MAINTENANCE_INTERVAL_DAYS,
                "contribution": float(overrun_contribution),
                "severity": "MEDIUM",
                "description": f"Maintenance overdue by {days_since - DEFAULT_MAINTENANCE_INTERVAL_DAYS:.0f} days",
            })

    # ── R3: Recent anomaly severity ──────────────────────────────────────────
    anomaly_contribution = 0.0
    for sev_str, count in anomaly_counts.items():
        try:
            sev = AnomalySeverity(sev_str)
            per_anomaly = ANOMALY_RISK_MAP.get(sev, 0.0)
            anomaly_contribution += min(0.30, count * per_anomaly)
        except ValueError:
            pass
    anomaly_contribution = min(0.30, anomaly_contribution)
    score += anomaly_contribution
    if anomaly_contribution > 0.05:
        total_anomalies = sum(anomaly_counts.values())
        factors.append({
            "factor": "recent_anomalies",
            "value": total_anomalies,
            "contribution": float(anomaly_contribution),
            "severity": "MEDIUM" if anomaly_contribution < 0.15 else "HIGH",
            "description": f"{total_anomalies} anomalies detected in past 30 days",
            "by_severity": anomaly_counts,
        })

    # ── R4: Fault history ────────────────────────────────────────────────────
    fault_count = features.get("fault_count", 0) or 0
    if fault_count >= 3:
        fault_contribution = min(0.15, fault_count * 0.05)
        score += fault_contribution
        factors.append({
            "factor": "fault_history",
            "value": int(fault_count),
            "contribution": float(fault_contribution),
            "severity": "MEDIUM",
            "description": f"{fault_count} faults recorded in maintenance history",
        })

    return min(1.0, score), factors


# ── Layer 2: Statistical trends ───────────────────────────────────────────────

def _layer2_trends(
    features: dict[str, Any],
    sensor_types: list[str],
) -> tuple[float, list[dict]]:
    """
    Compute trend-based risk score.
    Positive trend slope on critical sensors signals deterioration.
    Returns (score 0–1, list of contributing risk factors).
    """
    score = 0.0
    factors: list[dict] = []

    # Critical sensor types that directly indicate degradation when rising
    DEGRADATION_SENSORS = {"temperature", "vibration", "pressure"}
    # Sensors where a negative trend is concerning (dropping = problem)
    DROPPING_SENSORS = {"fluid_level", "voltage"}

    for sensor in sensor_types:
        slope = features.get(f"trend_slope_{sensor}")
        baseline_dev = features.get(f"baseline_deviation_{sensor}")
        threshold_freq = features.get(f"threshold_exceedance_freq_{sensor}", 0)

        # Trend slope contribution
        if slope is not None and abs(slope) > 0.1:
            if sensor in DEGRADATION_SENSORS and slope > 0:
                # Rising temperature/vibration/pressure = degradation
                slope_risk = min(0.20, abs(slope) * 0.05)
                score += slope_risk
                factors.append({
                    "factor": f"rising_trend_{sensor}",
                    "value": float(slope),
                    "contribution": float(slope_risk),
                    "severity": "MEDIUM" if slope_risk < 0.10 else "HIGH",
                    "description": f"{sensor} rising trend detected (slope={slope:.3f})",
                })
            elif sensor in DROPPING_SENSORS and slope < 0:
                # Falling fluid/voltage = problem
                slope_risk = min(0.20, abs(slope) * 0.05)
                score += slope_risk
                factors.append({
                    "factor": f"dropping_trend_{sensor}",
                    "value": float(slope),
                    "contribution": float(slope_risk),
                    "severity": "MEDIUM" if slope_risk < 0.10 else "HIGH",
                    "description": f"{sensor} dropping trend detected (slope={slope:.3f})",
                })

        # Baseline deviation contribution
        if baseline_dev is not None and abs(baseline_dev) > 0:
            rolling_std = features.get(f"rolling_std_{sensor}", 1.0) or 1.0
            if rolling_std > 0:
                dev_sigma = abs(baseline_dev) / rolling_std
                if dev_sigma >= 2.0:
                    dev_contribution = min(0.15, (dev_sigma - 2.0) * 0.03)
                    score += dev_contribution
                    factors.append({
                        "factor": f"baseline_deviation_{sensor}",
                        "value": float(baseline_dev),
                        "contribution": float(dev_contribution),
                        "severity": "MEDIUM",
                        "description": f"{sensor} deviated {dev_sigma:.1f}σ from baseline",
                    })

        # Threshold exceedance
        if threshold_freq is not None and threshold_freq > 0.05:
            exceedance_contribution = min(0.15, threshold_freq * 0.30)
            score += exceedance_contribution
            factors.append({
                "factor": f"threshold_exceedance_{sensor}",
                "value": float(threshold_freq),
                "contribution": float(exceedance_contribution),
                "severity": "HIGH" if threshold_freq > 0.20 else "MEDIUM",
                "description": f"{sensor} exceeded threshold in {threshold_freq:.0%} of readings",
            })

    return min(1.0, score), factors


# ── Layer 3: Ensemble aggregation ────────────────────────────────────────────

def _layer3_ensemble(
    l1_score: float,
    l2_score: float,
    data_sufficiency: float,
) -> tuple[float, float]:
    """
    Combine Layer 1 and Layer 2 scores using data-driven weights.
    When data is limited, rely more on rules (L1).
    Returns (combined_score, uncertainty).
    """
    # Weight layer 1 more when data is limited, layer 2 more when rich
    w1 = 0.40 + (1.0 - data_sufficiency) * 0.40  # 0.40–0.80
    w2 = 1.0 - w1
    combined = (w1 * l1_score + w2 * l2_score) / max(w1 + w2, 1e-9)

    # Uncertainty = spread between L1 and L2 scores
    # High disagreement between layers means higher uncertainty
    uncertainty = abs(l1_score - l2_score) * (1.0 - data_sufficiency * 0.5)
    uncertainty = min(1.0, uncertainty)

    return min(1.0, combined), uncertainty


# ── Data sufficiency ──────────────────────────────────────────────────────────

def _compute_data_sufficiency(features: dict[str, Any], n_sensor_types: int) -> float:
    """
    Estimate data sufficiency (0.0–1.0) based on how many feature values
    are available vs. None.
    """
    if not features:
        return 0.0
    non_null = sum(1 for v in features.values() if v is not None)
    total = max(1, len(features))
    base = non_null / total

    # Bonus for having multiple sensor types
    sensor_bonus = min(0.20, n_sensor_types * 0.04)
    return min(1.0, base + sensor_bonus)


# ── Per-component prediction ──────────────────────────────────────────────────

def predict_component_risk(
    component: Component,
    db: Session,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    persist: bool = True,
    pipeline_run_id: str | None = None,
) -> Prediction:
    """
    Generate a risk prediction for a single component.

    The prediction uses all data available up to `as_of` and must not
    access any data after that timestamp.

    Returns a Prediction ORM object. If persist=True, it is saved to DB.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    # ── Feature extraction ────────────────────────────────────────────────────
    features = compute_component_features(
        component=component,
        db=db,
        as_of=as_of,
        short_window_days=min(7, lookback_days),
        long_window_days=lookback_days,
    )

    # Determine which sensor types have data
    sensor_types = list({
        k.split("_")[-1] if k.startswith("rolling_mean_") else None
        for k in features.keys()
        if k.startswith("rolling_mean_")
    } - {None})

    data_sufficiency = _compute_data_sufficiency(features, len(sensor_types))

    # ── Anomaly aggregation ───────────────────────────────────────────────────
    cutoff_30d = as_of - timedelta(days=30)
    recent_anomalies = (
        db.query(AnomalyEvent)
        .filter(
            AnomalyEvent.component_id == component.id,
            AnomalyEvent.detected_at >= cutoff_30d,
            AnomalyEvent.detected_at <= as_of,
        )
        .all()
    )
    anomaly_counts: dict[str, int] = {}
    for ev in recent_anomalies:
        sev_val = ev.severity.value if hasattr(ev.severity, "value") else str(ev.severity)
        anomaly_counts[sev_val] = anomaly_counts.get(sev_val, 0) + 1

    # ── Layer 1: Rules ────────────────────────────────────────────────────────
    l1_score, l1_factors = _layer1_rules(component, features, anomaly_counts, as_of)

    # ── Layer 2: Statistical trends ───────────────────────────────────────────
    l2_score, l2_factors = _layer2_trends(features, sensor_types)

    # ── Layer 3: Ensemble ─────────────────────────────────────────────────────
    final_score, uncertainty = _layer3_ensemble(l1_score, l2_score, data_sufficiency)

    # Insufficient data guard: never assign LOW when data is very poor
    if data_sufficiency < 0.20 and final_score < 0.30:
        final_score = max(final_score, 0.30)
        uncertainty = max(uncertainty, 0.50)

    risk_category = _score_to_category(final_score)
    all_factors = l1_factors + l2_factors

    # Rank factors by contribution descending
    all_factors.sort(key=lambda x: x.get("contribution", 0), reverse=True)

    prediction = Prediction(
        id=uuid.uuid4(),
        asset_id=component.asset_id,
        component_id=component.id,
        predicted_at=as_of,
        prediction_horizon_days=lookback_days,
        risk_score=float(final_score),
        risk_category=risk_category,
        risk_factors=all_factors,
        feature_values={k: v for k, v in features.items() if v is not None},
        uncertainty=float(uncertainty),
        data_sufficiency=float(data_sufficiency),
        model_version=MODEL_VERSION,
        layer_scores={
            "layer1_rules": float(l1_score),
            "layer2_trends": float(l2_score),
            "layer3_ensemble": float(final_score),
            "data_sufficiency": float(data_sufficiency),
            "n_anomalies_30d": len(recent_anomalies),
        },
        pipeline_run_id=pipeline_run_id or MODEL_VERSION,
    )

    if persist:
        try:
            db.add(prediction)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                "Failed to persist prediction for component %s: %s", component.component_id, e
            )

    logger.debug(
        "Predicted %s risk for %s: score=%.3f category=%s",
        risk_category, component.component_id, final_score, risk_category,
    )
    return prediction


# ── Asset-level prediction ────────────────────────────────────────────────────

def run_risk_prediction_for_asset(
    asset: Asset,
    db: Session,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    persist: bool = True,
    pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Run risk prediction for all active components of an asset.
    Returns a summary dict with per-component predictions and asset-level rollup.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    run_id = pipeline_run_id or f"pred_{uuid.uuid4().hex[:8]}"
    components: list[Component] = (
        db.query(Component)
        .filter(Component.asset_id == asset.id, Component.is_active == True)
        .all()
    )

    component_results: list[dict] = []
    max_risk_score = 0.0
    max_risk_category = RiskCategory.LOW

    for component in components:
        try:
            pred = predict_component_risk(
                component=component,
                db=db,
                as_of=as_of,
                lookback_days=lookback_days,
                persist=persist,
                pipeline_run_id=run_id,
            )
            component_results.append({
                "component_id": str(component.id),
                "component_name": component.name,
                "component_type": component.component_type,
                "criticality": component.criticality,
                "risk_score": float(pred.risk_score),
                "risk_category": pred.risk_category.value if hasattr(pred.risk_category, "value") else str(pred.risk_category),
                "uncertainty": float(pred.uncertainty or 0),
                "data_sufficiency": float(pred.data_sufficiency or 0),
                "top_factors": (pred.risk_factors or [])[:3],
            })

            # Asset risk = worst single component risk (critical components weighted higher)
            component_risk = float(pred.risk_score)
            if component.criticality == "HIGH":
                component_risk = min(1.0, component_risk * 1.15)  # 15% weight boost
            if component_risk > max_risk_score:
                max_risk_score = component_risk
                max_risk_category = pred.risk_category

        except Exception as e:
            logger.error(
                "Risk prediction failed for component %s: %s",
                component.component_id, e
            )
            component_results.append({
                "component_id": str(component.id),
                "component_name": component.name,
                "error": str(e),
            })

    return {
        "asset_id": str(asset.id),
        "asset_identifier": asset.asset_id,
        "predicted_at": as_of.isoformat(),
        "overall_risk_score": float(max_risk_score),
        "overall_risk_category": max_risk_category.value if hasattr(max_risk_category, "value") else str(max_risk_category),
        "components_analyzed": len(component_results),
        "components": component_results,
        "pipeline_run_id": run_id,
    }


def run_risk_prediction_for_all_assets(
    db: Session,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    persist: bool = True,
) -> dict[str, Any]:
    """Run risk predictions for all active assets. Returns fleet-level summary."""
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    assets: list[Asset] = db.query(Asset).filter(Asset.is_active == True).all()
    logger.info("Running risk predictions for %d assets", len(assets))

    fleet_results: list[dict] = []
    risk_distribution: dict[str, int] = {cat.value: 0 for cat in RiskCategory}

    for asset in assets:
        result = run_risk_prediction_for_asset(
            asset=asset, db=db, as_of=as_of, lookback_days=lookback_days, persist=persist,
        )
        fleet_results.append(result)
        cat = result.get("overall_risk_category", "LOW")
        risk_distribution[cat] = risk_distribution.get(cat, 0) + 1

    logger.info("Fleet risk prediction complete: %d assets processed", len(fleet_results))

    return {
        "as_of": as_of.isoformat(),
        "assets_analyzed": len(fleet_results),
        "risk_distribution": risk_distribution,
        "assets": fleet_results,
    }

"""
Phase 10 — Explainability Service
====================================
Converts raw prediction and anomaly data into human-readable explanations.

Provides:
  explain_prediction(prediction) → structured explanation dict
  explain_anomaly(anomaly_event) → structured explanation dict
  generate_component_narrative(component, prediction, anomalies) → text summary

The explanation system is intentionally separated from the prediction
engine so explanations can be regenerated independently, augmented with
LLM output, or cached.

Note: LLM-augmented explanations (Gemini) are added via the copilot module.
      This module provides structured rule-based explanations that work
      without any LLM.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.models import AnomalyEvent, Component, Prediction, RiskCategory

logger = logging.getLogger(__name__)


def explain_prediction(prediction: Prediction) -> dict[str, Any]:
    """
    Convert a Prediction ORM object into a structured explanation.

    Returns a dict with:
      - summary: one-sentence text summary
      - risk_level: human-readable risk label
      - confidence: derived from uncertainty and data_sufficiency
      - key_factors: top 3 factors with plain-text descriptions
      - data_quality_note: note about data sufficiency
      - layer_breakdown: Layer 1/2/3 scores for transparency
    """
    risk_score = float(prediction.risk_score or 0)
    uncertainty = float(prediction.uncertainty or 0.5)
    data_suff = float(prediction.data_sufficiency or 0)
    risk_category = prediction.risk_category.value if hasattr(prediction.risk_category, "value") else str(prediction.risk_category)
    factors = prediction.risk_factors or []

    # Risk level label
    risk_labels = {
        "LOW": "Low Maintenance Risk",
        "MEDIUM": "Moderate Maintenance Risk",
        "HIGH": "High Maintenance Risk — Action Required",
        "CRITICAL": "Critical Risk — Immediate Attention Required",
    }
    risk_label = risk_labels.get(risk_category, risk_category)

    # Summary sentence
    if risk_score >= 0.75:
        summary = (
            f"This component has a CRITICAL maintenance risk score of {risk_score:.2f}. "
            "Immediate maintenance inspection is recommended."
        )
    elif risk_score >= 0.55:
        summary = (
            f"This component has a HIGH maintenance risk score of {risk_score:.2f}. "
            "Schedule maintenance before next operational use."
        )
    elif risk_score >= 0.30:
        summary = (
            f"This component has a MODERATE maintenance risk score of {risk_score:.2f}. "
            "Monitor closely and schedule maintenance at next opportunity."
        )
    else:
        summary = (
            f"This component has a LOW maintenance risk score of {risk_score:.2f}. "
            "Continue standard maintenance schedule."
        )

    # Confidence: high data sufficiency + low uncertainty = high confidence
    confidence = data_suff * (1.0 - uncertainty * 0.5)

    if confidence >= 0.70:
        confidence_label = "High Confidence"
    elif confidence >= 0.40:
        confidence_label = "Moderate Confidence"
    else:
        confidence_label = "Low Confidence — more data needed"

    # Data quality note
    if data_suff < 0.30:
        data_note = (
            "WARNING: Low data sufficiency. Prediction reliability is limited. "
            "Gather more sensor readings before acting on this assessment."
        )
    elif data_suff < 0.60:
        data_note = "Moderate data availability. Prediction may improve with more readings."
    else:
        data_note = "Sufficient historical data for reliable prediction."

    # Top factors in plain text
    key_factors = []
    for factor in factors[:3]:
        key_factors.append({
            "factor_name": factor.get("factor", "unknown"),
            "description": factor.get("description", ""),
            "severity": factor.get("severity", ""),
            "contribution": factor.get("contribution", 0),
        })

    # Layer breakdown
    layer_scores = prediction.layer_scores or {}

    return {
        "prediction_id": str(prediction.id),
        "component_id": str(prediction.component_id),
        "risk_score": risk_score,
        "risk_category": risk_category,
        "risk_level": risk_label,
        "summary": summary,
        "confidence": float(confidence),
        "confidence_label": confidence_label,
        "data_quality_note": data_note,
        "data_sufficiency": float(data_suff),
        "uncertainty": float(uncertainty),
        "key_factors": key_factors,
        "layer_breakdown": {
            "layer1_rules": float(layer_scores.get("layer1_rules", 0)),
            "layer2_trends": float(layer_scores.get("layer2_trends", 0)),
            "layer3_ensemble": float(layer_scores.get("layer3_ensemble", 0)),
        },
        "model_version": prediction.model_version or "unknown",
        "predicted_at": prediction.predicted_at.isoformat() if prediction.predicted_at else None,
    }


def explain_anomaly(anomaly: AnomalyEvent) -> dict[str, Any]:
    """
    Convert an AnomalyEvent ORM object into a structured explanation.

    Returns a dict with:
      - summary: one-sentence description
      - technical_details: z-score, methods, thresholds
      - recommended_action: suggested follow-up
    """
    evidence = anomaly.evidence or {}
    sensor_type = anomaly.sensor_type or "unknown"
    severity = anomaly.severity.value if hasattr(anomaly.severity, "value") else str(anomaly.severity)
    anomaly_type = anomaly.anomaly_type.value if hasattr(anomaly.anomaly_type, "value") else str(anomaly.anomaly_type)
    sensor_value = float(anomaly.sensor_value or 0)
    baseline_value = float(anomaly.baseline_value or 0)
    z_score = float(evidence.get("z_score", 0))
    methods = evidence.get("methods_triggered", [])

    # Summary
    deviation_pct = float(anomaly.deviation_pct or 0)
    direction = "above" if sensor_value > baseline_value else "below"
    summary = (
        f"{severity} anomaly on {sensor_type} sensor: value {sensor_value:.2f} is "
        f"{abs(deviation_pct):.1f}% {direction} baseline ({baseline_value:.2f}). "
        f"Detected by {len(methods)} method(s): {', '.join(methods)}."
    )

    # Recommended action
    action_map = {
        "CRITICAL": "Immediate inspection required. Suspend operations pending assessment.",
        "HIGH": "Investigate within 24 hours. Document findings and notify maintenance supervisor.",
        "MEDIUM": "Schedule inspection at next maintenance window. Monitor closely.",
        "LOW": "Log for trend analysis. No immediate action required.",
    }
    recommended_action = action_map.get(severity, "Review with maintenance team.")

    return {
        "anomaly_id": str(anomaly.id),
        "component_id": str(anomaly.component_id),
        "sensor_type": sensor_type,
        "severity": severity,
        "anomaly_type": anomaly_type,
        "summary": summary,
        "sensor_value": sensor_value,
        "baseline_value": baseline_value,
        "deviation_pct": float(deviation_pct),
        "z_score": float(z_score),
        "detection_methods": methods,
        "recommended_action": recommended_action,
        "detected_at": anomaly.detected_at.isoformat() if anomaly.detected_at else None,
        "is_acknowledged": bool(anomaly.is_acknowledged),
    }


def generate_component_narrative(
    component: Component,
    prediction: Prediction | None,
    recent_anomalies: list[AnomalyEvent],
) -> str:
    """
    Generate a concise plain-text narrative for a component's health status.
    Suitable for display in the UI without LLM augmentation.
    """
    lines = [f"Component: {component.name} ({component.component_type})"]

    # Operating hours context
    if component.current_operating_hours:
        dl = component.design_life_hours
        if dl:
            pct = component.current_operating_hours / dl * 100
            lines.append(
                f"  Operating hours: {component.current_operating_hours:.0f}/{dl:.0f} ({pct:.1f}% of design life)"
            )
        else:
            lines.append(f"  Operating hours: {component.current_operating_hours:.0f}")

    # Prediction summary
    if prediction:
        risk_score = float(prediction.risk_score or 0)
        risk_cat = prediction.risk_category.value if hasattr(prediction.risk_category, "value") else str(prediction.risk_category)
        lines.append(f"  Risk: {risk_cat} (score={risk_score:.2f})")
        if prediction.risk_factors:
            top = prediction.risk_factors[0]
            lines.append(f"  Primary driver: {top.get('description', top.get('factor', ''))}")
    else:
        lines.append("  Risk prediction: not available")

    # Anomaly summary
    if recent_anomalies:
        severity_counts: dict[str, int] = {}
        for a in recent_anomalies:
            sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        sev_summary = ", ".join(f"{v} {k}" for k, v in severity_counts.items())
        lines.append(f"  Recent anomalies (30d): {sev_summary}")
    else:
        lines.append("  Recent anomalies (30d): none detected")

    lines.append(f"\n{generate_disclaimer()}")
    return "\n".join(lines)


def generate_disclaimer() -> str:
    """Return the mandatory human-review disclaimer."""
    return (
        "AI-generated maintenance recommendations are decision-support outputs only. "
        "Final readiness and maintenance decisions require qualified human review."
    )

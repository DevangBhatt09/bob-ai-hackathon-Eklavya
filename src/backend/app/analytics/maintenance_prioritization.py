"""
Phase 11 — Maintenance Prioritization Engine
=============================================
Generates prioritized MaintenanceRecommendation records from predictions
and readiness assessments.

Priority tiers:
  IMMEDIATE — CRITICAL risk component or NOT_READY asset
  HIGH      — HIGH risk component or MAINTENANCE_REQUIRED asset
  PLANNED   — MEDIUM risk component
  MONITOR   — LOW risk, watch for trend changes

The engine:
  1. Iterates active assets and their component predictions
  2. Assigns priority based on risk score + asset criticality + overdue flag
  3. Persists MaintenanceRecommendation records to DB
  4. Returns a prioritised work order list sorted by urgency

Safety note:
  All outputs include the mandatory human-review disclaimer.
  Recommendations affect MAINTENANCE scheduling only.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    Asset,
    Component,
    MaintenancePriority,
    MaintenanceRecommendation,
    Prediction,
    RiskCategory,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

HUMAN_REVIEW_DISCLAIMER = (
    "AI-generated maintenance recommendations are decision-support outputs only. "
    "Final readiness and maintenance decisions require qualified human review."
)

# Hours budget estimate per priority tier (for planning)
HOURS_ESTIMATE: dict[str, float] = {
    MaintenancePriority.IMMEDIATE.value: 8.0,
    MaintenancePriority.HIGH.value: 4.0,
    MaintenancePriority.PLANNED.value: 2.0,
    MaintenancePriority.MONITOR.value: 0.5,
}


def _risk_to_priority(
    risk_category: str,
    component_criticality: str,
) -> MaintenancePriority:
    """
    Map risk category + component criticality to a maintenance priority.
    HIGH criticality components get escalated one tier.
    """
    cat_map = {
        "CRITICAL": MaintenancePriority.IMMEDIATE,
        "HIGH": MaintenancePriority.HIGH,
        "MEDIUM": MaintenancePriority.PLANNED,
        "LOW": MaintenancePriority.MONITOR,
    }
    base = cat_map.get(risk_category, MaintenancePriority.MONITOR)

    # Escalate HIGH criticality components
    if component_criticality == "HIGH":
        escalation = {
            MaintenancePriority.MONITOR: MaintenancePriority.PLANNED,
            MaintenancePriority.PLANNED: MaintenancePriority.HIGH,
            MaintenancePriority.HIGH: MaintenancePriority.HIGH,
            MaintenancePriority.IMMEDIATE: MaintenancePriority.IMMEDIATE,
        }
        return escalation.get(base, base)
    return base


def _build_recommendation_text(
    component: Component,
    prediction: Prediction,
    priority: MaintenancePriority,
) -> str:
    """Build the recommendation text for a maintenance work order."""
    risk_score = float(prediction.risk_score or 0)
    risk_cat = prediction.risk_category.value if hasattr(prediction.risk_category, "value") else str(prediction.risk_category)
    factors = prediction.risk_factors or []

    lines = [
        f"Maintenance recommendation for {component.name} ({component.component_type})",
        f"Priority: {priority.value} | Risk: {risk_cat} (score={risk_score:.2f})",
        "",
    ]

    if factors:
        lines.append("Key risk drivers:")
        for f in factors[:3]:
            lines.append(f"  - {f.get('description', f.get('factor', ''))}")
        lines.append("")

    action_map = {
        MaintenancePriority.IMMEDIATE: (
            "IMMEDIATE ACTION REQUIRED: Inspect and service this component before next operation. "
            "Do not operate until cleared by qualified maintenance personnel."
        ),
        MaintenancePriority.HIGH: (
            "Schedule maintenance within 48 hours. Detailed inspection and servicing recommended."
        ),
        MaintenancePriority.PLANNED: (
            "Schedule for maintenance at next available maintenance window. "
            "Continue monitoring sensor readings."
        ),
        MaintenancePriority.MONITOR: (
            "No immediate action required. Continue standard maintenance schedule. "
            "Monitor for trend changes."
        ),
    }
    lines.append(action_map.get(priority, "Review with maintenance team."))
    lines.append("")
    lines.append(HUMAN_REVIEW_DISCLAIMER)

    return "\n".join(lines)


def generate_maintenance_recommendations(
    asset: Asset,
    db: Session,
    as_of: datetime | None = None,
    pipeline_run_id: str | None = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    """
    Generate prioritized maintenance recommendations for all components of an asset.

    Reads the latest Prediction per component from DB (does not re-run predictions).
    Falls back to running predictions if no recent predictions exist.

    Returns a list of recommendation dicts sorted by priority.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    run_id = pipeline_run_id or f"maint_{uuid.uuid4().hex[:8]}"

    # Load active components
    components: list[Component] = (
        db.query(Component)
        .filter(Component.asset_id == asset.id, Component.is_active == True)
        .all()
    )

    recommendations: list[dict[str, Any]] = []
    rec_objects: list[MaintenanceRecommendation] = []

    for component in components:
        # Get latest prediction for this component
        prediction: Prediction | None = (
            db.query(Prediction)
            .filter(
                Prediction.component_id == component.id,
                Prediction.predicted_at <= as_of,
            )
            .order_by(Prediction.predicted_at.desc())
            .first()
        )

        # Skip MONITOR-level components with no meaningful risk signals
        if prediction is None:
            # No prediction available — treat as MEDIUM risk (unknown state)
            risk_cat = "MEDIUM"
            risk_score = 0.35
            priority = _risk_to_priority(risk_cat, component.criticality or "MEDIUM")
            rec_text = (
                f"No recent risk prediction for {component.name}. "
                "Inspect to establish baseline. "
                f"{HUMAN_REVIEW_DISCLAIMER}"
            )
            estimated_hours = HOURS_ESTIMATE.get(priority.value, 2.0)
        else:
            risk_cat = prediction.risk_category.value if hasattr(prediction.risk_category, "value") else str(prediction.risk_category)
            risk_score = float(prediction.risk_score or 0)
            priority = _risk_to_priority(risk_cat, component.criticality or "MEDIUM")
            rec_text = _build_recommendation_text(component, prediction, priority)
            estimated_hours = HOURS_ESTIMATE.get(priority.value, 2.0)

        # Build due date based on priority
        due_days = {
            MaintenancePriority.IMMEDIATE: 1,
            MaintenancePriority.HIGH: 7,
            MaintenancePriority.PLANNED: 30,
            MaintenancePriority.MONITOR: 90,
        }
        due_date = as_of + timedelta(days=due_days.get(priority, 30))

        rationale = {
            "risk_category": risk_cat,
            "risk_score": float(risk_score),
            "component_criticality": component.criticality,
            "priority_rationale": (
                f"Risk category {risk_cat} + criticality {component.criticality} → {priority.value}"
            ),
            "as_of": as_of.isoformat(),
        }

        if prediction:
            rationale["top_risk_factors"] = (prediction.risk_factors or [])[:3]
            rationale["data_sufficiency"] = float(prediction.data_sufficiency or 0)

        urgency_days_val = due_days.get(priority, 30)
        rec_obj = MaintenanceRecommendation(
            id=uuid.uuid4(),
            asset_id=asset.id,
            component_id=component.id,
            generated_at=as_of,
            priority=priority,
            issue_summary=f"{risk_cat} risk on {component.name} (score={risk_score:.2f})",
            evidence=[rationale],
            recommended_action=rec_text,
            urgency_days=urgency_days_val,
            prediction_window_days=30,
            risk_score=float(risk_score),
            data_confidence=float(rationale.get("data_sufficiency", 0.5)),
            human_review_required=True,
            review_status=ReviewStatus.PENDING,
            pipeline_run_id=run_id,
        )
        rec_objects.append(rec_obj)

        recommendations.append({
            "component_id": str(component.id),
            "component_name": component.name,
            "component_type": component.component_type,
            "criticality": component.criticality,
            "priority": priority.value,
            "risk_category": risk_cat,
            "risk_score": float(risk_score),
            "due_date": due_date.isoformat(),
            "estimated_hours": float(estimated_hours),
            "recommendation_text": rec_text,
        })

    # Sort by priority: IMMEDIATE > HIGH > PLANNED > MONITOR, then by risk_score desc
    priority_order = {
        MaintenancePriority.IMMEDIATE.value: 0,
        MaintenancePriority.HIGH.value: 1,
        MaintenancePriority.PLANNED.value: 2,
        MaintenancePriority.MONITOR.value: 3,
    }
    recommendations.sort(key=lambda r: (priority_order.get(r["priority"], 4), -r["risk_score"]))

    if persist and rec_objects:
        try:
            db.add_all(rec_objects)
            db.commit()
            logger.info(
                "Persisted %d maintenance recommendations for asset %s",
                len(rec_objects), asset.asset_id,
            )
        except Exception as e:
            db.rollback()
            logger.error(
                "Failed to persist recommendations for asset %s: %s", asset.asset_id, e
            )

    return recommendations


def run_maintenance_prioritization_for_all(
    db: Session,
    as_of: datetime | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Generate maintenance recommendations for all active assets.
    Returns a fleet-wide prioritized maintenance board.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    assets: list[Asset] = db.query(Asset).filter(Asset.is_active == True).all()
    all_recommendations: list[dict] = []
    priority_distribution: dict[str, int] = {p.value: 0 for p in MaintenancePriority}

    for asset in assets:
        recs = generate_maintenance_recommendations(
            asset=asset, db=db, as_of=as_of, persist=persist,
        )
        for rec in recs:
            rec["asset_id"] = str(asset.id)
            rec["asset_identifier"] = asset.asset_id
            all_recommendations.append(rec)
            p = rec.get("priority", "MONITOR")
            priority_distribution[p] = priority_distribution.get(p, 0) + 1

    # Sort fleet-wide: IMMEDIATE first
    priority_order = {
        MaintenancePriority.IMMEDIATE.value: 0,
        MaintenancePriority.HIGH.value: 1,
        MaintenancePriority.PLANNED.value: 2,
        MaintenancePriority.MONITOR.value: 3,
    }
    all_recommendations.sort(
        key=lambda r: (priority_order.get(r["priority"], 4), -r["risk_score"])
    )

    return {
        "as_of": as_of.isoformat(),
        "total_recommendations": len(all_recommendations),
        "priority_distribution": priority_distribution,
        "recommendations": all_recommendations,
        "disclaimer": HUMAN_REVIEW_DISCLAIMER,
    }

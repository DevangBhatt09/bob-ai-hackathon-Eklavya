"""
Phase 9 — Readiness Assessment Engine
========================================
Aggregates component-level risk predictions and data quality metrics
into an asset-level maintenance readiness status.

ReadinessStatus levels:
  READY               — All components LOW risk, data quality GOOD+
  READY_WITH_CAUTION  — Some MEDIUM risk components; no critical issues
  MAINTENANCE_REQUIRED— One or more HIGH risk components
  NOT_READY           — CRITICAL risk component or multiple HIGH risk
  INSUFFICIENT_DATA   — Missing/poor quality data; do not infer readiness

Safety rule:
  This assessment is MAINTENANCE readiness only, NOT mission/tactical
  readiness. All outputs must include the human-review disclaimer.

  Insufficient data NEVER implies READY. It always returns INSUFFICIENT_DATA.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.data_quality import compute_asset_data_quality
from app.analytics.risk_prediction import run_risk_prediction_for_asset
from app.models.models import (
    Asset,
    Component,
    DataQualityLevel,
    Prediction,
    ReadinessAssessment,
    ReadinessStatus,
    RiskCategory,
)

logger = logging.getLogger(__name__)

HUMAN_REVIEW_DISCLAIMER = (
    "AI-generated maintenance recommendations are decision-support outputs only. "
    "Final readiness and maintenance decisions require qualified human review."
)


def _determine_readiness_status(
    risk_summary: dict[str, Any],
    data_quality_score: float,
    quality_level: DataQualityLevel,
) -> tuple[ReadinessStatus, str]:
    """
    Translate risk summary + data quality into a ReadinessStatus.
    Returns (status, plain-text explanation).
    """
    # Insufficient data overrides everything
    if quality_level == DataQualityLevel.INSUFFICIENT or data_quality_score < 0.20:
        return (
            ReadinessStatus.INSUFFICIENT_DATA,
            "Insufficient sensor data to assess maintenance readiness. "
            "Do not infer readiness from absence of data.",
        )

    components = risk_summary.get("components", [])
    critical_components = [c for c in components if c.get("risk_category") == RiskCategory.CRITICAL.value]
    high_components = [c for c in components if c.get("risk_category") == RiskCategory.HIGH.value]
    medium_components = [c for c in components if c.get("risk_category") == RiskCategory.MEDIUM.value]

    # NOT_READY: any CRITICAL or 2+ HIGH risk components
    if critical_components or len(high_components) >= 2:
        comps_desc = ", ".join(c["component_name"] for c in (critical_components + high_components)[:3])
        return (
            ReadinessStatus.NOT_READY,
            f"Asset NOT READY for operations. Critical/high-risk components: {comps_desc}. "
            "Immediate maintenance assessment required.",
        )

    # MAINTENANCE_REQUIRED: single HIGH risk component
    if len(high_components) == 1:
        comp = high_components[0]
        return (
            ReadinessStatus.MAINTENANCE_REQUIRED,
            f"Maintenance required. Component '{comp['component_name']}' is at HIGH risk "
            f"(score={comp['risk_score']:.2f}). Schedule maintenance before next operational use.",
        )

    # READY_WITH_CAUTION: any MEDIUM risk components
    if medium_components:
        comps_desc = ", ".join(c["component_name"] for c in medium_components[:3])
        return (
            ReadinessStatus.READY_WITH_CAUTION,
            f"Asset ready with caution. Monitor: {comps_desc}. "
            "Schedule maintenance at next available opportunity.",
        )

    # READY: all LOW risk, good data quality
    overall_score = risk_summary.get("overall_risk_score", 0.0)
    return (
        ReadinessStatus.READY,
        f"All components at LOW risk (max score={overall_score:.2f}). "
        f"Asset appears ready for maintenance perspective. Data quality: {quality_level.value}.",
    )


def assess_asset_readiness(
    asset: Asset,
    db: Session,
    as_of: datetime | None = None,
    persist: bool = True,
    pipeline_run_id: str | None = None,
) -> ReadinessAssessment:
    """
    Compute maintenance readiness assessment for a single asset.

    Orchestrates:
      1. Risk prediction for all components
      2. Data quality evaluation
      3. Readiness status determination
      4. Persist ReadinessAssessment to DB

    Returns ReadinessAssessment ORM object.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    run_id = pipeline_run_id or f"readiness_{uuid.uuid4().hex[:8]}"

    # ── Step 1: Risk predictions ──────────────────────────────────────────────
    risk_summary = run_risk_prediction_for_asset(
        asset=asset,
        db=db,
        as_of=as_of,
        lookback_days=30,
        persist=False,  # Don't double-persist; caller can persist separately
        pipeline_run_id=run_id,
    )

    # ── Step 2: Data quality ──────────────────────────────────────────────────
    quality_metrics = compute_asset_data_quality(asset, db, window_days=30)
    data_quality_score = quality_metrics.overall_score
    quality_level = quality_metrics.quality_level

    # ── Step 3: Overall health score ─────────────────────────────────────────
    # Health score is inverse of risk, modulated by data quality
    max_risk = risk_summary.get("overall_risk_score", 0.5)
    # Penalise health when data quality is poor
    quality_weight = max(0.1, data_quality_score)
    health_score = (1.0 - max_risk) * quality_weight

    # ── Step 4: Readiness status ─────────────────────────────────────────────
    status, explanation = _determine_readiness_status(
        risk_summary, data_quality_score, quality_level
    )

    # Build component summary
    component_summary: dict[str, Any] = {
        "total": len(risk_summary.get("components", [])),
        "by_risk": {},
        "highest_risk": None,
    }
    for comp in risk_summary.get("components", []):
        cat = comp.get("risk_category", "LOW")
        component_summary["by_risk"][cat] = component_summary["by_risk"].get(cat, 0) + 1
        score = comp.get("risk_score", 0.0)
        if (
            component_summary["highest_risk"] is None
            or score > component_summary["highest_risk"].get("risk_score", 0)
        ):
            component_summary["highest_risk"] = comp

    # Primary evidence: top 3 risk factors across all components
    all_factors: list[dict] = []
    for comp in risk_summary.get("components", []):
        for factor in comp.get("top_factors", []):
            all_factors.append({**factor, "component_name": comp.get("component_name", "")})
    all_factors.sort(key=lambda x: x.get("contribution", 0), reverse=True)
    primary_evidence = all_factors[:5]

    assessment = ReadinessAssessment(
        id=uuid.uuid4(),
        asset_id=asset.id,
        assessed_at=as_of,
        status=status,
        overall_health_score=float(health_score),
        primary_evidence=primary_evidence,
        component_summary=component_summary,
        data_quality_score=float(data_quality_score),
        prediction_horizon_days=30,
        explanation=f"{explanation}\n\n{HUMAN_REVIEW_DISCLAIMER}",
        pipeline_run_id=run_id,
    )

    if persist:
        try:
            db.add(assessment)
            db.commit()
            logger.info(
                "Readiness assessment for %s: status=%s health=%.2f",
                asset.asset_id, status.value, health_score,
            )
        except Exception as e:
            db.rollback()
            logger.error(
                "Failed to persist readiness assessment for %s: %s", asset.asset_id, e
            )

    return assessment


def run_readiness_assessment_for_all_assets(
    db: Session,
    as_of: datetime | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Run readiness assessment for all active assets.
    Returns fleet-level summary with status distribution.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    assets: list[Asset] = db.query(Asset).filter(Asset.is_active == True).all()
    logger.info("Running readiness assessments for %d assets", len(assets))

    run_id = f"fleet_readiness_{uuid.uuid4().hex[:8]}"
    results: list[dict] = []
    status_distribution: dict[str, int] = {s.value: 0 for s in ReadinessStatus}

    for asset in assets:
        try:
            assessment = assess_asset_readiness(
                asset=asset, db=db, as_of=as_of, persist=persist, pipeline_run_id=run_id,
            )
            status_val = assessment.status.value if hasattr(assessment.status, "value") else str(assessment.status)
            status_distribution[status_val] = status_distribution.get(status_val, 0) + 1
            results.append({
                "asset_id": str(asset.id),
                "asset_identifier": asset.asset_id,
                "status": status_val,
                "health_score": float(assessment.overall_health_score or 0),
                "data_quality_score": float(assessment.data_quality_score or 0),
                "pipeline_run_id": run_id,
            })
        except Exception as e:
            logger.error("Readiness assessment failed for asset %s: %s", asset.asset_id, e)
            results.append({"asset_id": str(asset.id), "asset_identifier": asset.asset_id, "error": str(e)})

    logger.info("Fleet readiness complete: %s", status_distribution)

    return {
        "as_of": as_of.isoformat(),
        "assets_assessed": len(results),
        "status_distribution": status_distribution,
        "assets": results,
        "disclaimer": HUMAN_REVIEW_DISCLAIMER,
    }

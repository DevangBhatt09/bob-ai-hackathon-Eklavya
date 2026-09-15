"""Dashboard summary API — real fleet KPIs from database."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import (
    Asset, Component, AnomalyEvent, Prediction, ReadinessAssessment,
    SensorReading, AnomalySeverity, RiskCategory, ReadinessStatus
)

router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Fleet-wide dashboard KPIs — all computed from real DB data."""
    total_assets = db.query(Asset).filter(Asset.is_active == True).count()
    total_components = db.query(Component).filter(Component.is_active == True).count()
    total_readings = db.query(SensorReading).count()

    # Anomaly counts by severity
    anomaly_rows = (
        db.query(AnomalyEvent.severity, func.count(AnomalyEvent.id))
        .group_by(AnomalyEvent.severity)
        .all()
    )
    anomalies_by_severity = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in anomaly_rows}
    total_anomalies = sum(anomalies_by_severity.values())

    # Latest predictions risk distribution
    # Get the most recent prediction per component
    from sqlalchemy import text
    risk_rows = (
        db.query(Prediction.risk_category, func.count(Prediction.id))
        .group_by(Prediction.risk_category)
        .all()
    )
    risk_distribution = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in risk_rows}

    # Latest readiness status distribution
    readiness_rows = (
        db.query(ReadinessAssessment.status, func.count(ReadinessAssessment.id))
        .group_by(ReadinessAssessment.status)
        .all()
    )
    readiness_distribution = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in readiness_rows}

    # Fleet health score = avg health from latest readiness assessments
    health_score_avg = (
        db.query(func.avg(ReadinessAssessment.overall_health_score))
        .scalar()
    )

    # Critical alerts: CRITICAL anomalies not acknowledged
    critical_alerts = (
        db.query(AnomalyEvent)
        .filter(
            AnomalyEvent.severity == AnomalySeverity.CRITICAL,
            AnomalyEvent.is_acknowledged == False,
        )
        .count()
    )

    return {
        "fleet": {
            "total_assets": total_assets,
            "total_components": total_components,
            "total_sensor_readings": total_readings,
        },
        "anomalies": {
            "total": total_anomalies,
            "by_severity": anomalies_by_severity,
            "critical_unacknowledged": critical_alerts,
        },
        "risk_distribution": risk_distribution,
        "readiness_distribution": readiness_distribution,
        "fleet_health_score": float(health_score_avg) if health_score_avg else None,
        "pipeline_run_needed": total_anomalies == 0 and db.query(Prediction).count() == 0,
    }


@router.get("/fleet-health-matrix")
def get_fleet_health_matrix(db: Session = Depends(get_db)):
    """Fleet Health Matrix data: asset × component risk grid."""
    assets = db.query(Asset).filter(Asset.is_active == True).limit(20).all()
    matrix = []
    for asset in assets:
        components = (
            db.query(Component)
            .filter(Component.asset_id == asset.id, Component.is_active == True)
            .all()
        )
        comp_data = []
        for comp in components:
            latest_pred = (
                db.query(Prediction)
                .filter(Prediction.component_id == comp.id)
                .order_by(Prediction.predicted_at.desc())
                .first()
            )
            comp_data.append({
                "component_id": str(comp.id),
                "name": comp.name,
                "type": comp.component_type,
                "criticality": comp.criticality,
                "risk_score": float(latest_pred.risk_score) if latest_pred else None,
                "risk_category": (latest_pred.risk_category.value if hasattr(latest_pred.risk_category, "value") else str(latest_pred.risk_category)) if latest_pred else None,
            })
        latest_ra = (
            db.query(ReadinessAssessment)
            .filter(ReadinessAssessment.asset_id == asset.id)
            .order_by(ReadinessAssessment.assessed_at.desc())
            .first()
        )
        matrix.append({
            "asset_id": str(asset.id),
            "asset_identifier": asset.asset_id,
            "asset_name": asset.name,
            "asset_type": asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type),
            "fleet": asset.fleet,
            "health_score": float(latest_ra.overall_health_score) if latest_ra else None,
            "readiness_status": (latest_ra.status.value if hasattr(latest_ra.status, "value") else str(latest_ra.status)) if latest_ra else None,
            "components": comp_data,
        })
    return {"assets": matrix, "total": len(matrix)}


@router.get("/sensor-heatmap")
def get_sensor_heatmap(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """Sensor anomaly heatmap data: asset × sensor_type × day anomaly counts."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            AnomalyEvent.asset_id,
            AnomalyEvent.sensor_type,
            AnomalyEvent.severity,
            func.count(AnomalyEvent.id).label("count"),
        )
        .filter(AnomalyEvent.detected_at >= cutoff)
        .group_by(AnomalyEvent.asset_id, AnomalyEvent.sensor_type, AnomalyEvent.severity)
        .all()
    )

    # Build heatmap cells: {asset_id: {sensor_type: {severity: count}}}
    heatmap: dict = {}
    for row in rows:
        aid = str(row[0])
        st = row[1]
        sev = row[2].value if hasattr(row[2], "value") else str(row[2])
        cnt = row[3]
        if aid not in heatmap:
            heatmap[aid] = {}
        if st not in heatmap[aid]:
            heatmap[aid][st] = {}
        heatmap[aid][st][sev] = cnt

    return {"heatmap": heatmap, "days": days, "total_cells": len(rows)}

"""Anomalies API — real anomaly events from DB."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import AnomalyEvent, Asset, Component

router = APIRouter()


@router.get("")
def list_anomalies(
    skip: int = 0,
    limit: int = 50,
    severity: Optional[str] = None,
    asset_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(AnomalyEvent).filter(AnomalyEvent.detected_at >= cutoff)
    if severity:
        q = q.filter(AnomalyEvent.severity == severity.upper())
    if asset_id:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if asset:
            q = q.filter(AnomalyEvent.asset_id == asset.id)
    total = q.count()
    items = q.order_by(AnomalyEvent.detected_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(a.id),
                "asset_id": str(a.asset_id),
                "component_id": str(a.component_id) if a.component_id else None,
                "severity": a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                "anomaly_type": a.anomaly_type.value if hasattr(a.anomaly_type, "value") else str(a.anomaly_type),
                "sensor_type": a.sensor_type,
                "sensor_value": a.sensor_value,
                "baseline_value": a.baseline_value,
                "deviation_pct": a.deviation_pct,
                "anomaly_score": a.anomaly_score,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                "is_acknowledged": a.is_acknowledged,
                "evidence": a.evidence,
            }
            for a in items
        ],
    }


@router.patch("/{anomaly_id}/acknowledge")
def acknowledge_anomaly(anomaly_id: str, db: Session = Depends(get_db)):
    anomaly = db.query(AnomalyEvent).filter(AnomalyEvent.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    anomaly.is_acknowledged = True
    db.commit()
    return {"id": anomaly_id, "is_acknowledged": True}


@router.get("/timeline")
def get_anomaly_timeline(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Anomaly count per day for timeline chart."""
    from sqlalchemy import func, cast, Date
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            func.date_trunc("day", AnomalyEvent.detected_at).label("day"),
            AnomalyEvent.severity,
            func.count(AnomalyEvent.id).label("count"),
        )
        .filter(AnomalyEvent.detected_at >= cutoff)
        .group_by("day", AnomalyEvent.severity)
        .order_by("day")
        .all()
    )
    result = []
    for row in rows:
        result.append({
            "day": row[0].isoformat() if row[0] else None,
            "severity": row[1].value if hasattr(row[1], "value") else str(row[1]),
            "count": row[2],
        })
    return {"timeline": result}

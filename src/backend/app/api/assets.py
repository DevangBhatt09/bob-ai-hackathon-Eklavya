"""Assets API — full asset + component details."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import Asset, Component, SensorReading, Prediction, ReadinessAssessment

router = APIRouter()


@router.get("")
def list_assets(
    skip: int = 0,
    limit: int = 50,
    asset_type: Optional[str] = None,
    fleet: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Asset).filter(Asset.is_active == True)
    if asset_type:
        q = q.filter(Asset.asset_type == asset_type.upper())
    if fleet:
        q = q.filter(Asset.fleet.ilike(f"%{fleet}%"))
    total = q.count()
    assets = q.order_by(Asset.asset_id).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(a.id),
                "asset_id": a.asset_id,
                "name": a.name,
                "asset_type": a.asset_type.value if hasattr(a.asset_type, "value") else str(a.asset_type),
                "fleet": a.fleet,
                "location": a.location,
                "total_operating_hours": a.total_operating_hours,
                "total_cycles": a.total_cycles,
                "is_active": a.is_active,
            }
            for a in assets
        ],
    }


@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    components = db.query(Component).filter(Component.asset_id == asset.id, Component.is_active == True).all()

    # Latest readiness assessment
    latest_ra = (
        db.query(ReadinessAssessment)
        .filter(ReadinessAssessment.asset_id == asset.id)
        .order_by(ReadinessAssessment.assessed_at.desc())
        .first()
    )

    comp_list = []
    for comp in components:
        latest_pred = (
            db.query(Prediction)
            .filter(Prediction.component_id == comp.id)
            .order_by(Prediction.predicted_at.desc())
            .first()
        )
        comp_list.append({
            "id": str(comp.id),
            "component_id": comp.component_id,
            "name": comp.name,
            "component_type": comp.component_type,
            "criticality": comp.criticality,
            "current_operating_hours": comp.current_operating_hours,
            "design_life_hours": comp.design_life_hours,
            "life_utilisation": (
                comp.current_operating_hours / comp.design_life_hours
                if comp.design_life_hours and comp.current_operating_hours
                else None
            ),
            "risk_score": float(latest_pred.risk_score) if latest_pred else None,
            "risk_category": (latest_pred.risk_category.value if hasattr(latest_pred.risk_category, "value") else str(latest_pred.risk_category)) if latest_pred else None,
        })

    return {
        "id": str(asset.id),
        "asset_id": asset.asset_id,
        "name": asset.name,
        "asset_type": asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type),
        "fleet": asset.fleet,
        "location": asset.location,
        "serial_number": asset.serial_number,
        "total_operating_hours": asset.total_operating_hours,
        "total_cycles": asset.total_cycles,
        "is_active": asset.is_active,
        "components": comp_list,
        "readiness": {
            "status": (latest_ra.status.value if hasattr(latest_ra.status, "value") else str(latest_ra.status)) if latest_ra else None,
            "health_score": float(latest_ra.overall_health_score) if latest_ra and latest_ra.overall_health_score else None,
            "assessed_at": latest_ra.assessed_at.isoformat() if latest_ra and latest_ra.assessed_at else None,
        },
    }


@router.get("/{asset_id}/sensor-history")
def get_sensor_history(
    asset_id: str,
    sensor_type: Optional[str] = None,
    component_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Sensor reading history for degradation timeline chart."""
    from datetime import datetime, timedelta, timezone
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        db.query(SensorReading)
        .filter(SensorReading.asset_id == asset.id, SensorReading.timestamp >= cutoff)
    )
    if sensor_type:
        q = q.filter(SensorReading.sensor_type == sensor_type)
    if component_id:
        comp = db.query(Component).filter(Component.component_id == component_id).first()
        if comp:
            q = q.filter(SensorReading.component_id == comp.id)

    readings = q.order_by(SensorReading.timestamp).limit(2000).all()
    return {
        "asset_id": asset_id,
        "sensor_type": sensor_type,
        "total": len(readings),
        "readings": [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "sensor_type": r.sensor_type,
                "sensor_value": r.sensor_value,
                "unit": r.unit,
                "quality_flag": r.quality_flag,
                "component_id": str(r.component_id) if r.component_id else None,
            }
            for r in readings
        ],
    }

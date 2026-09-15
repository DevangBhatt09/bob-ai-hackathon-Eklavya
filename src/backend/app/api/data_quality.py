"""Data Quality API."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import Asset, DataQualityReport

router = APIRouter()


@router.get("")
def list_data_quality(
    skip: int = 0,
    limit: int = 50,
    quality_level: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(DataQualityReport)
    if quality_level:
        q = q.filter(DataQualityReport.quality_level == quality_level.upper())
    total = q.count()
    items = q.order_by(DataQualityReport.report_date.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "asset_id": str(r.asset_id),
                "report_date": r.report_date.isoformat() if r.report_date else None,
                "quality_level": r.quality_level.value if hasattr(r.quality_level, "value") else str(r.quality_level),
                "overall_score": float(r.overall_score),
                "completeness_score": float(r.completeness_score),
                "validity_score": float(r.validity_score),
                "consistency_score": float(r.consistency_score),
                "timeliness_score": float(r.timeliness_score),
                "duplicate_rate": float(r.duplicate_rate),
                "missing_value_rate": float(r.missing_value_rate),
                "outlier_rate": float(r.outlier_rate),
                "total_records": r.total_records,
            }
            for r in items
        ],
    }


@router.get("/asset/{asset_id}")
def get_asset_data_quality(asset_id: str, db: Session = Depends(get_db)):
    """Compute and return real-time data quality for an asset."""
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    from app.analytics.data_quality import compute_asset_data_quality
    metrics = compute_asset_data_quality(asset, db, window_days=30)
    return {
        "asset_id": asset_id,
        "quality_level": metrics.quality_level.value if hasattr(metrics.quality_level, "value") else str(metrics.quality_level),
        "overall_score": float(metrics.overall_score),
        "completeness": float(metrics.completeness),
        "validity": float(metrics.validity),
        "consistency": float(metrics.consistency),
        "timeliness": float(metrics.timeliness),
        "duplicate_rate": float(metrics.duplicate_rate),
        "missing_value_rate": float(metrics.missing_value_rate),
        "outlier_rate": float(metrics.outlier_rate),
        "total_records": metrics.total_records,
        "issues_detail": metrics.issues_detail,
    }


@router.get("/fleet-summary")
def get_fleet_data_quality_summary(db: Session = Depends(get_db)):
    """Fleet-wide data quality distribution (latest reports)."""
    rows = (
        db.query(DataQualityReport.quality_level, func.count(DataQualityReport.id))
        .group_by(DataQualityReport.quality_level)
        .all()
    )
    distribution = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in rows}
    avg_score = db.query(func.avg(DataQualityReport.overall_score)).scalar()
    return {
        "distribution": distribution,
        "average_overall_score": float(avg_score) if avg_score else None,
        "total_reports": sum(distribution.values()),
    }

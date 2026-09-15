"""Readiness Assessment API."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import ReadinessAssessment, Asset

router = APIRouter()


@router.get("")
def list_readiness(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ReadinessAssessment)
    if status:
        q = q.filter(ReadinessAssessment.status == status.upper())
    total = q.count()
    items = q.order_by(ReadinessAssessment.assessed_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "asset_id": str(r.asset_id),
                "assessed_at": r.assessed_at.isoformat() if r.assessed_at else None,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "overall_health_score": float(r.overall_health_score) if r.overall_health_score is not None else None,
                "data_quality_score": float(r.data_quality_score) if r.data_quality_score is not None else None,
                "component_summary": r.component_summary,
                "explanation": r.explanation,
                "primary_evidence": r.primary_evidence,
                "pipeline_run_id": r.pipeline_run_id,
            }
            for r in items
        ],
    }


@router.get("/asset/{asset_id}")
def get_asset_readiness(asset_id: str, db: Session = Depends(get_db)):
    """Get latest readiness assessment for an asset."""
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    assessment = (
        db.query(ReadinessAssessment)
        .filter(ReadinessAssessment.asset_id == asset.id)
        .order_by(ReadinessAssessment.assessed_at.desc())
        .first()
    )
    if not assessment:
        return {"asset_id": asset_id, "status": "NO_ASSESSMENT", "message": "Run pipeline to generate assessment"}
    return {
        "id": str(assessment.id),
        "asset_id": asset_id,
        "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None,
        "status": assessment.status.value if hasattr(assessment.status, "value") else str(assessment.status),
        "overall_health_score": float(assessment.overall_health_score) if assessment.overall_health_score is not None else None,
        "data_quality_score": float(assessment.data_quality_score) if assessment.data_quality_score is not None else None,
        "component_summary": assessment.component_summary,
        "explanation": assessment.explanation,
        "primary_evidence": assessment.primary_evidence,
    }

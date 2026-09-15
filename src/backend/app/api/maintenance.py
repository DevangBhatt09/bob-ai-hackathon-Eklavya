"""Maintenance Recommendations API."""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import MaintenanceRecommendation, ReviewStatus, Component, Asset

router = APIRouter()


@router.get("")
def list_maintenance(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    total = db.query(MaintenanceRecommendation).count()
    items = (
        db.query(MaintenanceRecommendation)
        .order_by(MaintenanceRecommendation.risk_score.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for r in items:
        comp = db.query(Component).filter(Component.id == r.component_id).first()
        asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
        result.append({
            "id": str(r.id),
            "asset_id": str(r.asset_id),
            "asset_identifier": asset.asset_id if asset else None,
            "component_id": str(r.component_id),
            "component_name": comp.name if comp else None,
            "component_type": comp.component_type if comp else None,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
            "issue_summary": r.issue_summary,
            "recommended_action": r.recommended_action,
            "urgency_days": r.urgency_days,
            "risk_score": float(r.risk_score) if r.risk_score is not None else None,
            "data_confidence": float(r.data_confidence) if r.data_confidence is not None else None,
            "human_review_required": r.human_review_required,
            "review_status": r.review_status.value if hasattr(r.review_status, "value") else str(r.review_status),
            "reviewer_notes": r.reviewer_notes,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "evidence": r.evidence,
        })
    return {"total": total, "items": result}


@router.get("/priorities")
def maintenance_priorities(db: Session = Depends(get_db)):
    """Get top maintenance recommendations sorted by priority and risk score."""
    items = (
        db.query(MaintenanceRecommendation)
        .order_by(MaintenanceRecommendation.risk_score.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
                "issue_summary": r.issue_summary,
                "review_status": r.review_status.value if hasattr(r.review_status, "value") else str(r.review_status),
                "risk_score": float(r.risk_score) if r.risk_score is not None else None,
            }
            for r in items
        ]
    }


class ReviewUpdate(BaseModel):
    review_status: str
    reviewer_notes: Optional[str] = None
    reviewed_by: Optional[str] = None


@router.patch("/{rec_id}/review")
def update_review(rec_id: str, update: ReviewUpdate, db: Session = Depends(get_db)):
    rec = db.query(MaintenanceRecommendation).filter(
        MaintenanceRecommendation.id == uuid.UUID(rec_id)
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.review_status = ReviewStatus(update.review_status)
    rec.reviewer_notes = update.reviewer_notes
    rec.reviewed_by = update.reviewed_by
    rec.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "id": rec_id,
        "review_status": rec.review_status.value if hasattr(rec.review_status, "value") else str(rec.review_status),
    }

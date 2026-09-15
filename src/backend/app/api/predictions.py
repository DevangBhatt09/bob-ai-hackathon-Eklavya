"""Predictions API — real risk prediction results."""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import Prediction, Asset, Component

router = APIRouter()


@router.get("")
def list_predictions(
    skip: int = 0,
    limit: int = 50,
    risk_category: Optional[str] = None,
    asset_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Prediction)
    if risk_category:
        q = q.filter(Prediction.risk_category == risk_category.upper())
    if asset_id:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if asset:
            q = q.filter(Prediction.asset_id == asset.id)
    total = q.count()
    items = q.order_by(Prediction.predicted_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(p.id),
                "asset_id": str(p.asset_id),
                "component_id": str(p.component_id),
                "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
                "risk_score": float(p.risk_score),
                "risk_category": p.risk_category.value if hasattr(p.risk_category, "value") else str(p.risk_category),
                "uncertainty": float(p.uncertainty) if p.uncertainty is not None else None,
                "data_sufficiency": float(p.data_sufficiency) if p.data_sufficiency is not None else None,
                "risk_factors": p.risk_factors,
                "layer_scores": p.layer_scores,
                "model_version": p.model_version,
            }
            for p in items
        ],
    }


@router.get("/{prediction_id}/explain")
def explain_prediction(prediction_id: str, db: Session = Depends(get_db)):
    """Get human-readable explanation for a prediction."""
    pred = db.query(Prediction).filter(Prediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    from app.analytics.explainability import explain_prediction as _explain
    return _explain(pred)


@router.get("/failure-risk-horizon")
def get_failure_risk_horizon(
    top_n: int = Query(20, ge=5, le=55),
    db: Session = Depends(get_db),
):
    """
    Failure-Risk Horizon: highest-risk components across the fleet.
    Returns components sorted by risk_score descending for horizon chart.
    """
    # Get most recent prediction per component via subquery
    from sqlalchemy import func
    latest_subq = (
        db.query(
            Prediction.component_id,
            func.max(Prediction.predicted_at).label("max_ts"),
        )
        .group_by(Prediction.component_id)
        .subquery()
    )
    preds = (
        db.query(Prediction)
        .join(
            latest_subq,
            (Prediction.component_id == latest_subq.c.component_id)
            & (Prediction.predicted_at == latest_subq.c.max_ts),
        )
        .order_by(Prediction.risk_score.desc())
        .limit(top_n)
        .all()
    )

    horizon = []
    for pred in preds:
        comp = db.query(Component).filter(Component.id == pred.component_id).first()
        asset = db.query(Asset).filter(Asset.id == pred.asset_id).first()
        horizon.append({
            "component_id": str(pred.component_id),
            "component_name": comp.name if comp else "Unknown",
            "component_type": comp.component_type if comp else None,
            "criticality": comp.criticality if comp else None,
            "asset_identifier": asset.asset_id if asset else None,
            "asset_name": asset.name if asset else None,
            "risk_score": float(pred.risk_score),
            "risk_category": pred.risk_category.value if hasattr(pred.risk_category, "value") else str(pred.risk_category),
            "uncertainty": float(pred.uncertainty) if pred.uncertainty is not None else None,
            "top_factor": (pred.risk_factors[0]["description"] if pred.risk_factors else None),
            "predicted_at": pred.predicted_at.isoformat() if pred.predicted_at else None,
        })
    return {"horizon": horizon, "total": len(horizon)}

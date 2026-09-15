"""Pipeline API — triggers full analytics pipeline runs."""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db, SessionLocal

router = APIRouter()


def _run_full_pipeline(asset_id: str | None = None):
    """Run full analytics pipeline (anomaly → prediction → readiness → recommendations)."""
    import logging
    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        from app.models.models import Asset
        from app.analytics.anomaly_detection import run_anomaly_detection_for_asset
        from app.analytics.risk_prediction import run_risk_prediction_for_asset
        from app.analytics.readiness_assessment import assess_asset_readiness
        from app.analytics.maintenance_prioritization import generate_maintenance_recommendations

        if asset_id:
            assets = db.query(Asset).filter(Asset.asset_id == asset_id, Asset.is_active == True).all()
        else:
            assets = db.query(Asset).filter(Asset.is_active == True).all()

        as_of = datetime.now(timezone.utc)
        logger.info("Pipeline starting for %d assets", len(assets))

        for asset in assets:
            try:
                # Phase 7: Anomaly detection
                run_anomaly_detection_for_asset(asset, db, lookback_days=365, as_of=as_of, persist=True)
                # Phase 8: Risk prediction
                run_risk_prediction_for_asset(asset, db, as_of=as_of, lookback_days=365, persist=True)
                # Phase 9: Readiness assessment
                assess_asset_readiness(asset, db, as_of=as_of, persist=True)
                # Phase 11: Maintenance recommendations
                generate_maintenance_recommendations(asset, db, as_of=as_of, persist=True)
            except Exception as e:
                logger.error("Pipeline failed for asset %s: %s", asset.asset_id, e)

        logger.info("Pipeline complete for %d assets", len(assets))
    except Exception as e:
        logger.error("Pipeline run failed: %s", e)
    finally:
        db.close()


@router.post("/run")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    asset_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Trigger full analytics pipeline. Runs in background."""
    from app.models.models import Asset
    if asset_id:
        asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    background_tasks.add_task(_run_full_pipeline, asset_id)
    return {
        "status": "started",
        "message": f"Pipeline started for {'asset ' + asset_id if asset_id else 'all assets'}",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/run-sync")
def run_pipeline_sync(
    asset_id: str | None = None,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """
    Run pipeline synchronously for a small subset (for testing/demo).
    Processes up to `limit` assets.
    """
    from app.models.models import Asset
    from app.analytics.anomaly_detection import run_anomaly_detection_for_asset
    from app.analytics.risk_prediction import run_risk_prediction_for_asset
    from app.analytics.readiness_assessment import assess_asset_readiness
    from app.analytics.maintenance_prioritization import generate_maintenance_recommendations

    if asset_id:
        assets = db.query(Asset).filter(Asset.asset_id == asset_id, Asset.is_active == True).all()
    else:
        assets = db.query(Asset).filter(Asset.is_active == True).limit(limit).all()

    as_of = datetime.now(timezone.utc)
    results = []
    for asset in assets:
        try:
            anomaly_result = run_anomaly_detection_for_asset(asset, db, lookback_days=365, as_of=as_of, persist=True)
            pred_result = run_risk_prediction_for_asset(asset, db, as_of=as_of, lookback_days=365, persist=True)
            readiness = assess_asset_readiness(asset, db, as_of=as_of, persist=True)
            generate_maintenance_recommendations(asset, db, as_of=as_of, persist=True)
            results.append({
                "asset_id": asset.asset_id,
                "anomalies_detected": anomaly_result.anomalies_detected,
                "overall_risk": pred_result.get("overall_risk_category"),
                "readiness_status": readiness.status.value if hasattr(readiness.status, "value") else str(readiness.status),
            })
        except Exception as e:
            results.append({"asset_id": asset.asset_id, "error": str(e)})

    return {
        "status": "complete",
        "assets_processed": len(results),
        "results": results,
        "as_of": as_of.isoformat(),
    }

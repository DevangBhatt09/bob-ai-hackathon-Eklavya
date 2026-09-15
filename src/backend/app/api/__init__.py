"""
API router — aggregates all sub-routers.
"""
from fastapi import APIRouter

from app.api import (
    assets,
    anomalies,
    copilot,
    dashboard,
    data_quality,
    ingestion,
    maintenance,
    pipeline,
    predictions,
    readiness,
)

router = APIRouter()

router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
router.include_router(assets.router, prefix="/assets", tags=["assets"])
router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
router.include_router(maintenance.router, prefix="/maintenance", tags=["maintenance"])
router.include_router(readiness.router, prefix="/readiness", tags=["readiness"])
router.include_router(data_quality.router, prefix="/data-quality", tags=["data-quality"])
router.include_router(ingestion.router, prefix="/ingestion", tags=["ingestion"])
router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
router.include_router(copilot.router, prefix="/copilot", tags=["copilot"])

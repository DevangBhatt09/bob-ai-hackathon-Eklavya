"""
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup/shutdown lifecycle."""
    logger.info("Starting %s in %s mode", settings.app_name, settings.environment)
    logger.info("Database: %s", settings.database_url.split("@")[-1])  # no credentials in log
    logger.info("Gemini available: %s", settings.gemini_available)
    yield
    logger.info("Application shutdown.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Predictive maintenance and asset-readiness platform. "
            "AI-generated recommendations are decision-support outputs only. "
            "Final decisions require qualified human review."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # Import here to avoid circular imports at module level
    from app.api import router as api_router  # noqa: PLC0415
    app.include_router(api_router, prefix="/api")

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        return {
            "status": "ok",
            "application": settings.app_name,
            "environment": settings.environment,
            "gemini_configured": settings.gemini_available,
        }

    return app


app = create_app()

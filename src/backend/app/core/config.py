"""
Application configuration using pydantic-settings.
All secrets come from environment variables / .env file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_name: str = "Mission Readiness & Predictive Maintenance Copilot"
    environment: Literal["development", "production", "test"] = "development"
    secret_key: str = "change-me-in-production"
    debug: bool = False

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+psycopg://hums_user:hums_password@localhost:5432/hums_db"
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # ── Gemini ─────────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_timeout_seconds: float = 20.0

    # ── Synthetic data ─────────────────────────────────────────────────────────
    synthetic_data_seed: int = 42

    # ── Analytics ─────────────────────────────────────────────────────────────
    anomaly_zscore_threshold: float = 3.0
    anomaly_iqr_multiplier: float = 1.5
    risk_critical_threshold: float = 0.80
    risk_high_threshold: float = 0.60
    risk_medium_threshold: float = 0.35

    @field_validator("database_url")
    @classmethod
    def must_be_postgresql(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must use postgresql driver")
        return v

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def gemini_available(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

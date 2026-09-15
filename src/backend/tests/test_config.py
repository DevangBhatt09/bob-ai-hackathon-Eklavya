"""
Tests for core application config.
"""
import pytest
from pydantic import ValidationError


class TestSettings:
    def test_default_settings_load(self):
        """Settings can be loaded with defaults."""
        from app.core.config import Settings
        s = Settings(DATABASE_URL="postgresql+psycopg://user:pass@localhost/testdb")
        assert s.environment == "development"
        assert s.gemini_available is False  # empty key by default

    def test_database_url_must_be_postgresql(self):
        """Settings rejects non-PostgreSQL DATABASE_URL."""
        from app.core.config import Settings
        # Use model_validate to bypass env-file reading
        with pytest.raises((ValidationError, ValueError)):
            Settings.model_validate(
                {"database_url": "sqlite:///./test.db"},
                context={"_env_file": None},
            )

    def test_gemini_available_when_key_set(self):
        """gemini_available returns True when key is configured."""
        from app.core.config import Settings
        # Construct with explicit values — env vars shouldn't override model_validate
        s = Settings.model_construct(
            database_url="postgresql+psycopg://user:pass@localhost/testdb",
            gemini_api_key="some-api-key",
            risk_critical_threshold=0.80,
            risk_high_threshold=0.60,
            risk_medium_threshold=0.35,
        )
        assert s.gemini_available is True

    def test_risk_thresholds_ordering(self):
        """Risk thresholds are in correct descending order."""
        from app.core.config import Settings
        s = Settings(DATABASE_URL="postgresql+psycopg://user:pass@localhost/testdb")
        assert s.risk_critical_threshold > s.risk_high_threshold > s.risk_medium_threshold

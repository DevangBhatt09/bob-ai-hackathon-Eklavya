"""
Tests for Phase 9 — Readiness Assessment Engine.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.analytics.readiness_assessment import _determine_readiness_status, assess_asset_readiness
from app.models.models import (
    DataQualityLevel,
    ReadinessAssessment,
    ReadinessStatus,
    RiskCategory,
)


# ── Unit tests: _determine_readiness_status ───────────────────────────────────

def _risk_summary(
    *,
    components: list[dict] | None = None,
    overall_risk_score: float = 0.1,
) -> dict:
    return {
        "components": components or [],
        "overall_risk_score": overall_risk_score,
    }


class TestDetermineReadinessStatus:
    def test_insufficient_data_quality_overrides_all(self):
        # Even if risk is low, insufficient data → INSUFFICIENT_DATA
        summary = _risk_summary(
            components=[{"risk_category": "LOW", "component_name": "Eng", "risk_score": 0.1}]
        )
        status, explanation = _determine_readiness_status(
            summary, data_quality_score=0.10, quality_level=DataQualityLevel.INSUFFICIENT
        )
        assert status == ReadinessStatus.INSUFFICIENT_DATA
        assert "Insufficient" in explanation

    def test_very_low_quality_score_overrides(self):
        # quality_score < 0.20 triggers INSUFFICIENT_DATA regardless of level enum
        summary = _risk_summary(
            components=[{"risk_category": "LOW", "component_name": "Eng", "risk_score": 0.1}]
        )
        status, _ = _determine_readiness_status(
            summary, data_quality_score=0.15, quality_level=DataQualityLevel.FAIR
        )
        assert status == ReadinessStatus.INSUFFICIENT_DATA

    def test_critical_component_is_not_ready(self):
        summary = _risk_summary(
            components=[
                {"risk_category": "CRITICAL", "component_name": "Main Engine", "risk_score": 0.85}
            ]
        )
        status, explanation = _determine_readiness_status(
            summary, data_quality_score=0.80, quality_level=DataQualityLevel.GOOD
        )
        assert status == ReadinessStatus.NOT_READY
        assert "NOT READY" in explanation

    def test_two_high_components_is_not_ready(self):
        summary = _risk_summary(
            components=[
                {"risk_category": "HIGH", "component_name": "Gearbox", "risk_score": 0.65},
                {"risk_category": "HIGH", "component_name": "Rotor Head", "risk_score": 0.68},
            ]
        )
        status, _ = _determine_readiness_status(
            summary, data_quality_score=0.80, quality_level=DataQualityLevel.GOOD
        )
        assert status == ReadinessStatus.NOT_READY

    def test_single_high_component_is_maintenance_required(self):
        summary = _risk_summary(
            components=[
                {"risk_category": "HIGH", "component_name": "Gearbox", "risk_score": 0.62},
                {"risk_category": "LOW", "component_name": "Fuel Pump", "risk_score": 0.12},
            ]
        )
        status, explanation = _determine_readiness_status(
            summary, data_quality_score=0.80, quality_level=DataQualityLevel.GOOD
        )
        assert status == ReadinessStatus.MAINTENANCE_REQUIRED
        assert "maintenance" in explanation.lower()

    def test_medium_component_is_ready_with_caution(self):
        summary = _risk_summary(
            components=[
                {"risk_category": "MEDIUM", "component_name": "Filter", "risk_score": 0.42},
                {"risk_category": "LOW", "component_name": "Fuel Pump", "risk_score": 0.12},
            ]
        )
        status, _ = _determine_readiness_status(
            summary, data_quality_score=0.80, quality_level=DataQualityLevel.GOOD
        )
        assert status == ReadinessStatus.READY_WITH_CAUTION

    def test_all_low_is_ready(self):
        summary = _risk_summary(
            components=[
                {"risk_category": "LOW", "component_name": "Engine", "risk_score": 0.10},
                {"risk_category": "LOW", "component_name": "Gearbox", "risk_score": 0.15},
            ]
        )
        status, _ = _determine_readiness_status(
            summary, data_quality_score=0.90, quality_level=DataQualityLevel.EXCELLENT
        )
        assert status == ReadinessStatus.READY

    def test_no_components_defaults_ready(self):
        # No components → no risk signals → READY (but low risk score)
        summary = _risk_summary(components=[])
        status, _ = _determine_readiness_status(
            summary, data_quality_score=0.85, quality_level=DataQualityLevel.GOOD
        )
        assert status == ReadinessStatus.READY


# ── Integration: assess_asset_readiness ──────────────────────────────────────

class TestAssessAssetReadiness:
    def test_returns_readiness_assessment(self, db_session, sample_asset):
        result = assess_asset_readiness(sample_asset, db_session, persist=False)
        assert isinstance(result, ReadinessAssessment)

    def test_status_is_valid_enum(self, db_session, sample_asset):
        result = assess_asset_readiness(sample_asset, db_session, persist=False)
        assert result.status in list(ReadinessStatus)

    def test_health_score_in_range(self, db_session, sample_asset):
        result = assess_asset_readiness(sample_asset, db_session, persist=False)
        assert result.overall_health_score is not None
        assert 0.0 <= result.overall_health_score <= 1.0

    def test_disclaimer_in_explanation(self, db_session, sample_asset):
        result = assess_asset_readiness(sample_asset, db_session, persist=False)
        # The disclaimer must appear somewhere in the assessment (explanation or evidence)
        combined = (result.explanation or "") + str(result.primary_evidence or "")
        assert "human review" in combined.lower()

    def test_persist_saves_to_db(self, db_session, sample_asset):
        assess_asset_readiness(sample_asset, db_session, persist=True)
        count = (
            db_session.query(ReadinessAssessment)
            .filter(ReadinessAssessment.asset_id == sample_asset.id)
            .count()
        )
        assert count >= 1

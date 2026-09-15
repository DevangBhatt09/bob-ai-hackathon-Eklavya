"""
Tests for Phase 8 — Risk/Failure Prediction Engine.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.analytics.risk_prediction import (
    _score_to_category,
    _layer1_rules,
    predict_component_risk,
    run_risk_prediction_for_asset,
)
from app.models.models import (
    AnomalySeverity,
    Prediction,
    RiskCategory,
)


# ── Unit tests: _score_to_category ────────────────────────────────────────────

class TestScoreToCategory:
    def test_critical_at_boundary(self):
        assert _score_to_category(0.75) == RiskCategory.CRITICAL

    def test_critical_above(self):
        assert _score_to_category(0.90) == RiskCategory.CRITICAL
        assert _score_to_category(1.0) == RiskCategory.CRITICAL

    def test_high_at_boundary(self):
        assert _score_to_category(0.55) == RiskCategory.HIGH

    def test_high_range(self):
        assert _score_to_category(0.60) == RiskCategory.HIGH
        assert _score_to_category(0.74) == RiskCategory.HIGH

    def test_medium_at_boundary(self):
        assert _score_to_category(0.30) == RiskCategory.MEDIUM

    def test_medium_range(self):
        assert _score_to_category(0.40) == RiskCategory.MEDIUM
        assert _score_to_category(0.54) == RiskCategory.MEDIUM

    def test_low(self):
        assert _score_to_category(0.0) == RiskCategory.LOW
        assert _score_to_category(0.29) == RiskCategory.LOW


# ── Helpers: build mock component via SimpleNamespace ─────────────────────────

def _mock_component(
    *,
    design_life_hours: float | None = 2000.0,
    current_operating_hours: float = 500.0,
    criticality: str = "MEDIUM",
) -> SimpleNamespace:
    """
    Build a duck-typed component-like object usable with _layer1_rules.
    SimpleNamespace avoids SQLAlchemy instrumentation issues.
    """
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        asset_id=str(uuid.uuid4()),
        component_id="TEST-COMP-001",
        name="Test Engine",
        component_type="engine",
        criticality=criticality,
        design_life_hours=design_life_hours,
        current_operating_hours=current_operating_hours,
        current_cycles=100,
    )


# ── Unit tests: _layer1_rules ─────────────────────────────────────────────────

class TestLayer1Rules:
    def test_new_component_low_risk(self):
        comp = _mock_component(design_life_hours=2000.0, current_operating_hours=100.0)
        features = {"days_since_maintenance": 30, "fault_count": 0}
        score, factors = _layer1_rules(comp, features, {}, datetime.now(timezone.utc))
        assert score < 0.30  # LOW risk expected
        assert isinstance(factors, list)

    def test_high_life_utilisation_raises_score(self):
        # 92% design life = CRITICAL utilisation
        comp = _mock_component(design_life_hours=2000.0, current_operating_hours=1840.0)
        features = {"days_since_maintenance": 30, "fault_count": 0}
        score, factors = _layer1_rules(comp, features, {}, datetime.now(timezone.utc))
        assert score >= 0.40
        factor_names = [f["factor"] for f in factors]
        assert "design_life_utilisation" in factor_names

    def test_overdue_maintenance_raises_score(self):
        comp = _mock_component(design_life_hours=2000.0, current_operating_hours=500.0)
        # 200 days since maintenance (> 90-day default interval)
        features = {"days_since_maintenance": 200, "fault_count": 0}
        score, factors = _layer1_rules(comp, features, {}, datetime.now(timezone.utc))
        factor_names = [f["factor"] for f in factors]
        assert "maintenance_interval_overrun" in factor_names

    def test_critical_anomalies_raise_score(self):
        comp = _mock_component(design_life_hours=2000.0, current_operating_hours=500.0)
        features = {"days_since_maintenance": 30, "fault_count": 0}
        # 2 CRITICAL anomalies
        anomaly_counts = {AnomalySeverity.CRITICAL.value: 2}
        score, factors = _layer1_rules(comp, features, anomaly_counts, datetime.now(timezone.utc))
        factor_names = [f["factor"] for f in factors]
        assert "recent_anomalies" in factor_names
        assert score > 0.40

    def test_score_capped_at_1(self):
        comp = _mock_component(design_life_hours=2000.0, current_operating_hours=1999.0)
        features = {"days_since_maintenance": 400, "fault_count": 10}
        anomaly_counts = {
            AnomalySeverity.CRITICAL.value: 5,
            AnomalySeverity.HIGH.value: 5,
        }
        score, _ = _layer1_rules(comp, features, anomaly_counts, datetime.now(timezone.utc))
        assert 0.0 <= score <= 1.0

    def test_no_design_life_skips_util_factor(self):
        comp = _mock_component(design_life_hours=None, current_operating_hours=500.0)
        features = {"days_since_maintenance": 30, "fault_count": 0}
        score, factors = _layer1_rules(comp, features, {}, datetime.now(timezone.utc))
        factor_names = [f["factor"] for f in factors]
        assert "design_life_utilisation" not in factor_names


# ── Integration: predict_component_risk ──────────────────────────────────────

class TestPredictComponentRisk:
    def test_returns_prediction_object(self, db_session, sample_component):
        result = predict_component_risk(sample_component, db=db_session, persist=False)
        assert isinstance(result, Prediction)

    def test_risk_score_in_range(self, db_session, sample_component):
        pred = predict_component_risk(sample_component, db=db_session, persist=False)
        assert 0.0 <= float(pred.risk_score) <= 1.0

    def test_risk_category_valid(self, db_session, sample_component):
        pred = predict_component_risk(sample_component, db=db_session, persist=False)
        assert pred.risk_category in list(RiskCategory)

    def test_prediction_fields_populated(self, db_session, sample_component):
        pred = predict_component_risk(sample_component, db=db_session, persist=False)
        assert isinstance(pred.risk_factors, list)
        assert pred.uncertainty is not None
        assert pred.data_sufficiency is not None
        assert pred.model_version is not None


# ── Integration: run_risk_prediction_for_asset ────────────────────────────────

class TestRunRiskPredictionForAsset:
    def test_returns_dict(self, db_session, sample_asset, sample_component):
        result = run_risk_prediction_for_asset(asset=sample_asset, db=db_session)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self, db_session, sample_asset, sample_component):
        result = run_risk_prediction_for_asset(asset=sample_asset, db=db_session)
        for key in ["asset_id", "overall_risk_score", "overall_risk_category", "components"]:
            assert key in result, f"Missing key: {key}"

    def test_components_list_populated(self, db_session, sample_asset, sample_component):
        result = run_risk_prediction_for_asset(asset=sample_asset, db=db_session)
        assert len(result["components"]) >= 1

    def test_overall_risk_score_in_range(self, db_session, sample_asset, sample_component):
        result = run_risk_prediction_for_asset(asset=sample_asset, db=db_session)
        assert 0.0 <= result["overall_risk_score"] <= 1.0

    def test_prediction_persisted_to_db(self, db_session, sample_asset, sample_component):
        run_risk_prediction_for_asset(asset=sample_asset, db=db_session, persist=True)
        count = (
            db_session.query(Prediction)
            .filter(Prediction.asset_id == sample_asset.id)
            .count()
        )
        assert count >= 1

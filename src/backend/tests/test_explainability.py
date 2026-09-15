"""
Tests for Phase 10 — Explainability Service.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.analytics.explainability import (
    explain_anomaly,
    explain_prediction,
    generate_component_narrative,
    generate_disclaimer,
)
from app.models.models import (
    AnomalySeverity,
    AnomalyType,
    RiskCategory,
)


# ── Helpers: mock ORM objects via SimpleNamespace ─────────────────────────────

def _make_prediction(
    *,
    risk_score: float = 0.65,
    risk_category: RiskCategory = RiskCategory.HIGH,
    uncertainty: float = 0.30,
    data_sufficiency: float = 0.75,
    risk_factors: list | None = None,
    layer_scores: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        asset_id=str(uuid.uuid4()),
        component_id=str(uuid.uuid4()),
        predicted_at=datetime.now(timezone.utc),
        prediction_horizon_days=30,
        risk_score=risk_score,
        risk_category=risk_category,
        risk_factors=risk_factors or [
            {"factor": "design_life_utilisation", "description": "90% of design life consumed", "severity": "CRITICAL", "contribution": 0.45}
        ],
        uncertainty=uncertainty,
        data_sufficiency=data_sufficiency,
        model_version="prediction_v1",
        layer_scores=layer_scores or {"layer1_rules": 0.60, "layer2_trends": 0.55, "layer3_ensemble": 0.65},
    )


def _make_anomaly(
    *,
    severity: AnomalySeverity = AnomalySeverity.HIGH,
    sensor_type: str = "temperature",
    sensor_value: float = 95.0,
    baseline_value: float = 75.0,
    deviation_pct: float = 26.7,
    evidence: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        asset_id=str(uuid.uuid4()),
        component_id=str(uuid.uuid4()),
        sensor_type=sensor_type,
        detected_at=datetime.now(timezone.utc),
        anomaly_type=AnomalyType.ZSCORE_OUTLIER,
        severity=severity,
        anomaly_score=0.85,
        sensor_value=sensor_value,
        baseline_value=baseline_value,
        deviation_pct=deviation_pct,
        evidence=evidence or {"z_score": 3.5, "methods_triggered": ["zscore", "iqr"]},
        is_acknowledged=False,
    )


def _make_component() -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        asset_id=str(uuid.uuid4()),
        component_id="COMP-001",
        name="Main Engine",
        component_type="engine",
        criticality="HIGH",
        design_life_hours=2000.0,
        current_operating_hours=1800.0,
        current_cycles=500,
    )


# ── explain_prediction ────────────────────────────────────────────────────────

class TestExplainPrediction:
    def test_returns_dict_with_required_keys(self):
        pred = _make_prediction()
        result = explain_prediction(pred)
        for key in ["prediction_id", "risk_score", "risk_category", "risk_level", "summary",
                    "confidence", "confidence_label", "data_quality_note", "key_factors",
                    "layer_breakdown"]:
            assert key in result, f"Missing key: {key}"

    def test_critical_prediction_summary(self):
        pred = _make_prediction(risk_score=0.85, risk_category=RiskCategory.CRITICAL)
        result = explain_prediction(pred)
        assert "CRITICAL" in result["summary"]

    def test_high_prediction_summary(self):
        pred = _make_prediction(risk_score=0.60, risk_category=RiskCategory.HIGH)
        result = explain_prediction(pred)
        assert "HIGH" in result["summary"]

    def test_medium_prediction_summary(self):
        pred = _make_prediction(risk_score=0.40, risk_category=RiskCategory.MEDIUM)
        result = explain_prediction(pred)
        assert "MODERATE" in result["summary"]

    def test_low_prediction_summary(self):
        pred = _make_prediction(risk_score=0.15, risk_category=RiskCategory.LOW)
        result = explain_prediction(pred)
        assert "LOW" in result["summary"]

    def test_high_confidence_label(self):
        pred = _make_prediction(uncertainty=0.10, data_sufficiency=0.90)
        result = explain_prediction(pred)
        assert "High Confidence" in result["confidence_label"]

    def test_low_confidence_label(self):
        pred = _make_prediction(uncertainty=0.80, data_sufficiency=0.20)
        result = explain_prediction(pred)
        assert "Low Confidence" in result["confidence_label"]

    def test_low_data_warning_in_note(self):
        pred = _make_prediction(data_sufficiency=0.20)
        result = explain_prediction(pred)
        assert "WARNING" in result["data_quality_note"]

    def test_key_factors_populated(self):
        pred = _make_prediction(
            risk_factors=[
                {"factor": "design_life_utilisation", "description": "90% of life consumed", "severity": "CRITICAL", "contribution": 0.45},
                {"factor": "recent_anomalies", "description": "3 anomalies", "severity": "HIGH", "contribution": 0.25},
            ]
        )
        result = explain_prediction(pred)
        assert len(result["key_factors"]) == 2
        assert result["key_factors"][0]["factor_name"] == "design_life_utilisation"

    def test_layer_breakdown_values(self):
        pred = _make_prediction(
            layer_scores={"layer1_rules": 0.60, "layer2_trends": 0.50, "layer3_ensemble": 0.62}
        )
        result = explain_prediction(pred)
        lb = result["layer_breakdown"]
        assert lb["layer1_rules"] == pytest.approx(0.60)
        assert lb["layer2_trends"] == pytest.approx(0.50)
        assert lb["layer3_ensemble"] == pytest.approx(0.62)


# ── explain_anomaly ───────────────────────────────────────────────────────────

class TestExplainAnomaly:
    def test_returns_dict_with_required_keys(self):
        anomaly = _make_anomaly()
        result = explain_anomaly(anomaly)
        for key in ["anomaly_id", "sensor_type", "severity", "summary",
                    "sensor_value", "baseline_value", "recommended_action",
                    "is_acknowledged"]:
            assert key in result, f"Missing key: {key}"

    def test_critical_action(self):
        anomaly = _make_anomaly(severity=AnomalySeverity.CRITICAL)
        result = explain_anomaly(anomaly)
        assert "Immediate inspection" in result["recommended_action"]

    def test_high_action(self):
        anomaly = _make_anomaly(severity=AnomalySeverity.HIGH)
        result = explain_anomaly(anomaly)
        assert "24 hours" in result["recommended_action"]

    def test_low_action(self):
        anomaly = _make_anomaly(severity=AnomalySeverity.LOW)
        result = explain_anomaly(anomaly)
        assert "No immediate action" in result["recommended_action"]

    def test_summary_contains_sensor_type(self):
        anomaly = _make_anomaly(sensor_type="vibration")
        result = explain_anomaly(anomaly)
        assert "vibration" in result["summary"]

    def test_is_acknowledged_false_by_default(self):
        anomaly = _make_anomaly()
        result = explain_anomaly(anomaly)
        assert result["is_acknowledged"] is False


# ── generate_component_narrative ──────────────────────────────────────────────

class TestGenerateComponentNarrative:
    def test_returns_string(self):
        comp = _make_component()
        narrative = generate_component_narrative(comp, None, [])
        assert isinstance(narrative, str)

    def test_contains_component_name(self):
        comp = _make_component()
        narrative = generate_component_narrative(comp, None, [])
        assert "Main Engine" in narrative

    def test_contains_disclaimer(self):
        comp = _make_component()
        narrative = generate_component_narrative(comp, None, [])
        assert "human review" in narrative.lower()

    def test_with_prediction_shows_risk(self):
        comp = _make_component()
        pred = _make_prediction(risk_score=0.80, risk_category=RiskCategory.CRITICAL)
        pred.component_id = comp.id
        narrative = generate_component_narrative(comp, pred, [])
        assert "CRITICAL" in narrative

    def test_with_anomalies_shows_count(self):
        comp = _make_component()
        anomalies = [_make_anomaly(severity=AnomalySeverity.HIGH) for _ in range(3)]
        for a in anomalies:
            a.component_id = comp.id
        narrative = generate_component_narrative(comp, None, anomalies)
        assert "3" in narrative or "HIGH" in narrative

    def test_no_prediction_shows_not_available(self):
        comp = _make_component()
        narrative = generate_component_narrative(comp, None, [])
        assert "not available" in narrative


# ── generate_disclaimer ───────────────────────────────────────────────────────

class TestGenerateDisclaimer:
    def test_disclaimer_text(self):
        d = generate_disclaimer()
        assert "human review" in d.lower()
        assert "AI-generated" in d
        assert len(d) > 50

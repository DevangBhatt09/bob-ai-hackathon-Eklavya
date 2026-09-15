"""
Tests for Phase 11 — Maintenance Prioritization Engine.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.analytics.maintenance_prioritization import (
    _risk_to_priority,
    generate_maintenance_recommendations,
)
from app.models.models import (
    MaintenancePriority,
    MaintenanceRecommendation,
)


# ── Unit tests: _risk_to_priority ─────────────────────────────────────────────

class TestRiskToPriority:
    def test_critical_risk_is_immediate(self):
        assert _risk_to_priority("CRITICAL", "MEDIUM") == MaintenancePriority.IMMEDIATE

    def test_critical_risk_high_criticality_is_immediate(self):
        assert _risk_to_priority("CRITICAL", "HIGH") == MaintenancePriority.IMMEDIATE

    def test_high_risk_medium_criticality(self):
        assert _risk_to_priority("HIGH", "MEDIUM") == MaintenancePriority.HIGH

    def test_high_risk_high_criticality_stays_high(self):
        # HIGH risk + HIGH criticality: both maps to HIGH (no escalation above HIGH)
        assert _risk_to_priority("HIGH", "HIGH") == MaintenancePriority.HIGH

    def test_medium_risk_medium_criticality_is_planned(self):
        assert _risk_to_priority("MEDIUM", "MEDIUM") == MaintenancePriority.PLANNED

    def test_medium_risk_high_criticality_escalates(self):
        # MEDIUM risk but HIGH criticality → escalates to HIGH
        assert _risk_to_priority("MEDIUM", "HIGH") == MaintenancePriority.HIGH

    def test_low_risk_medium_criticality_is_monitor(self):
        assert _risk_to_priority("LOW", "MEDIUM") == MaintenancePriority.MONITOR

    def test_low_risk_high_criticality_escalates(self):
        # LOW risk but HIGH criticality → PLANNED
        assert _risk_to_priority("LOW", "HIGH") == MaintenancePriority.PLANNED

    def test_unknown_risk_defaults_to_monitor(self):
        assert _risk_to_priority("UNKNOWN", "MEDIUM") == MaintenancePriority.MONITOR


# ── Integration: generate_maintenance_recommendations ─────────────────────────

class TestGenerateMaintenanceRecommendations:
    def test_returns_list(self, db_session, sample_asset, sample_component):
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        assert isinstance(results, list)

    def test_at_least_one_recommendation(self, db_session, sample_asset, sample_component):
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        assert len(results) >= 1

    def test_recommendation_has_required_keys(self, db_session, sample_asset, sample_component):
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        rec = results[0]
        for key in ["component_id", "component_name", "priority", "risk_score",
                    "recommendation_text"]:
            assert key in rec, f"Missing key: {key}"

    def test_priority_is_valid_enum_value(self, db_session, sample_asset, sample_component):
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        valid = {p.value for p in MaintenancePriority}
        for rec in results:
            assert rec["priority"] in valid

    def test_disclaimer_in_all_recommendation_texts(self, db_session, sample_asset, sample_component):
        """The human-review disclaimer must appear in the recommendation_text."""
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        for rec in results:
            assert "human review" in rec.get("recommendation_text", "").lower(), (
                f"Disclaimer missing from: {rec.get('recommendation_text', '')[:80]}"
            )

    def test_persists_to_db(self, db_session, sample_asset, sample_component):
        # First run predictions so there's data to recommend from
        from app.analytics.risk_prediction import run_risk_prediction_for_asset
        run_risk_prediction_for_asset(asset=sample_asset, db=db_session, persist=True)

        generate_maintenance_recommendations(
            sample_asset, db_session, persist=True
        )
        count = (
            db_session.query(MaintenanceRecommendation)
            .filter(MaintenanceRecommendation.asset_id == sample_asset.id)
            .count()
        )
        assert count >= 1

    def test_results_sorted_by_priority(self, db_session, sample_asset, sample_component):
        """Recommendations should be sorted highest-priority first."""
        results = generate_maintenance_recommendations(
            sample_asset, db_session, persist=False
        )
        if len(results) < 2:
            return  # can't test sort with one item

        priority_order = {
            "IMMEDIATE": 0, "HIGH": 1, "PLANNED": 2, "MONITOR": 3
        }
        for i in range(len(results) - 1):
            p_current = priority_order.get(results[i]["priority"], 99)
            p_next = priority_order.get(results[i + 1]["priority"], 99)
            assert p_current <= p_next, (
                f"Out of order: {results[i]['priority']} before {results[i+1]['priority']}"
            )

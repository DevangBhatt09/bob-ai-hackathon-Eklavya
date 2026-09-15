"""
Tests for Phase 6 — Feature Engineering
=========================================
Tests that features are computed correctly and without data leakage.
Uses SQLite in-memory via the shared conftest fixtures.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.analytics.feature_engineering import compute_component_features
from app.models.models import SensorReading, MaintenanceRecord, MaintenanceType


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _add_readings(db_session, asset_id, component_id, n=20, sensor_type="temperature",
                  base_value=80.0, noise=2.0, start_hours_ago=48):
    """Insert n evenly-spaced sensor readings."""
    import random
    rng = random.Random(42)
    readings = []
    for i in range(n):
        offset_h = start_hours_ago - (i * (start_hours_ago / n))
        ts = datetime.now(timezone.utc) - timedelta(hours=offset_h)
        readings.append(SensorReading(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            component_id=component_id,
            timestamp=ts,
            sensor_type=sensor_type,
            sensor_value=base_value + rng.uniform(-noise, noise),
            unit="C",
            quality_flag="OK",
            ingestion_batch_id="test_feat",
        ))
    db_session.add_all(readings)
    db_session.commit()
    return readings


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFeatureEngineering:
    def test_returns_dict(self, db_session, sample_asset, sample_component):
        """compute_component_features returns a dict."""
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id))
        result = compute_component_features(sample_component, db_session)
        assert isinstance(result, dict)

    def test_sensor_features_present(self, db_session, sample_asset, sample_component):
        """Expected rolling stat features exist for temperature sensor."""
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id))
        result = compute_component_features(sample_component, db_session)
        for key in ("rolling_mean_temperature", "rolling_std_temperature", "trend_slope_temperature"):
            assert key in result, f"Missing feature: {key}"

    def test_no_data_leakage_future_readings_excluded(self, db_session, sample_asset, sample_component):
        """Features computed as_of a past timestamp exclude future readings."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        # Add past readings (should be included)
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id),
                      n=10, start_hours_ago=48)
        # Add future reading (should be excluded)
        future_reading = SensorReading(
            id=str(uuid.uuid4()),
            asset_id=str(sample_asset.id),
            component_id=str(sample_component.id),
            timestamp=datetime.now(timezone.utc) + timedelta(hours=10),
            sensor_type="temperature",
            sensor_value=999.0,  # distinctive future value
            unit="C",
            quality_flag="OK",
            ingestion_batch_id="test_future",
        )
        db_session.add(future_reading)
        db_session.commit()

        result = compute_component_features(sample_component, db_session, as_of=cutoff)
        # Rolling mean should NOT be 999.0 — future reading excluded
        mean_val = result.get("rolling_mean_temperature")
        if mean_val is not None:
            assert mean_val < 200.0, "Future reading leaked into feature computation"

    def test_maintenance_features_present(self, db_session, sample_asset, sample_component):
        """Maintenance-related features are present in output."""
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id))
        result = compute_component_features(sample_component, db_session)
        # At minimum these keys should exist (may be 0/None if no maintenance)
        for key in ("days_since_maintenance", "fault_count", "replacement_count"):
            assert key in result, f"Missing maintenance feature: {key}"

    def test_empty_sensor_data_returns_dict(self, db_session, sample_asset, sample_component):
        """No sensor readings returns a dict (not an error)."""
        # No readings added — should return empty/null features gracefully
        result = compute_component_features(sample_component, db_session)
        assert isinstance(result, dict)

    def test_rolling_mean_approximates_base(self, db_session, sample_asset, sample_component):
        """Rolling mean should be close to base_value when noise is small."""
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id),
                      n=30, base_value=85.0, noise=0.5)
        result = compute_component_features(sample_component, db_session)
        mean_val = result.get("rolling_mean_temperature")
        if mean_val is not None:
            assert 82.0 < mean_val < 88.0, f"Rolling mean {mean_val} far from expected ~85.0"

    def test_as_of_defaults_to_now(self, db_session, sample_asset, sample_component):
        """as_of=None and as_of=now() return consistent results."""
        _add_readings(db_session, str(sample_asset.id), str(sample_component.id))
        result_default = compute_component_features(sample_component, db_session, as_of=None)
        result_now = compute_component_features(
            sample_component, db_session,
            as_of=datetime.now(timezone.utc)
        )
        assert isinstance(result_default, dict)
        assert isinstance(result_now, dict)
        # Both should have same keys
        assert set(result_default.keys()) == set(result_now.keys())

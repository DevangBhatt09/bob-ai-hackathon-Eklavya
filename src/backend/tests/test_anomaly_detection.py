"""
Tests for Phase 7 — Anomaly Detection Engine
=============================================
Tests z-score, IQR, and ensemble detection methods using in-memory data.
"""
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.analytics.anomaly_detection import (
    _zscore_flags,
    _iqr_flags,
    _classify_severity,
    run_anomaly_detection_for_asset,
    AnomalyDetectionResult,
    MIN_READINGS_FOR_DETECTION,
    ZSCORE_THRESHOLD,
)
from app.models.models import AnomalySeverity, SensorReading


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_clean_readings(asset_id, component_id, n=50, base=80.0, noise=1.0):
    """Generate n SensorReadings with small random noise around base."""
    rng = np.random.default_rng(42)
    readings = []
    for i in range(n):
        ts = datetime.now(timezone.utc) - timedelta(hours=(n - i))
        readings.append(SensorReading(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            component_id=component_id,
            timestamp=ts,
            sensor_type="temperature",
            sensor_value=float(base + rng.normal(0, noise)),
            unit="C",
            quality_flag="OK",
            ingestion_batch_id="test_anomaly",
        ))
    return readings


def _make_readings_with_spike(asset_id, component_id, n=50, spike_value=200.0, spike_index=45):
    """Generate readings with one obvious spike."""
    readings = _make_clean_readings(asset_id, component_id, n)
    readings[spike_index].sensor_value = spike_value
    return readings


# ─── Unit tests for detection primitives ─────────────────────────────────────

class TestZScoreFlags:
    def test_clean_series_no_flags(self):
        """Flat clean series with small noise → no z-score flags."""
        rng = np.random.default_rng(42)
        values = 80.0 + rng.normal(0, 1.0, 50)
        flags = _zscore_flags(values)
        # Should flag very few (noise level won't reach ZSCORE_THRESHOLD=3)
        assert flags.sum() <= 2  # allow 0-2 false positives

    def test_obvious_spike_flagged(self):
        """Single obvious spike → flagged when baseline has variance."""
        rng = np.random.default_rng(1)
        values = 80.0 + rng.normal(0, 0.5, 50)  # small normal noise (std=0.5)
        values[45] = 200.0  # >> 3 sigma spike
        flags = _zscore_flags(values)
        assert flags[45] == True

    def test_first_point_never_flagged(self):
        """First point cannot have a lookback → never flagged."""
        rng = np.random.default_rng(2)
        values = 80.0 + rng.normal(0, 1.0, 50)
        values[0] = 999.0  # spike at position 0
        flags = _zscore_flags(values)
        assert flags[0] == False


class TestIQRFlags:
    def test_clean_series_no_flags(self):
        """Normal distribution values → very few IQR flags."""
        rng = np.random.default_rng(42)
        values = 80.0 + rng.normal(0, 1.0, 50)
        flags = _iqr_flags(values)
        assert flags.sum() <= 3

    def test_extreme_outlier_flagged(self):
        """Value far outside IQR range → flagged."""
        rng = np.random.default_rng(3)
        values = 80.0 + rng.normal(0, 0.5, 50)
        values[40] = 500.0  # >> IQR fence
        flags = _iqr_flags(values)
        assert flags[40] == True


class TestSeverityClassification:
    def test_critical_requires_3_votes_and_high_z(self):
        sev = _classify_severity(150.0, 80.0, 2.0, votes=3)
        # z = (150-80)/2 = 35 → CRITICAL
        assert sev == AnomalySeverity.CRITICAL

    def test_low_with_small_deviation(self):
        sev = _classify_severity(83.0, 80.0, 2.0, votes=2)
        # z = (83-80)/2 = 1.5 → LOW
        assert sev == AnomalySeverity.LOW

    def test_single_vote_always_low(self):
        sev = _classify_severity(120.0, 80.0, 2.0, votes=1)
        assert sev == AnomalySeverity.LOW


# ─── Integration tests ────────────────────────────────────────────────────────

class TestAnomalyDetectionIntegration:
    def test_clean_data_no_anomalies(self, db_session, sample_asset, sample_component):
        """Clean readings → no anomaly events detected."""
        readings = _make_clean_readings(
            str(sample_asset.id), str(sample_component.id), n=60
        )
        db_session.add_all(readings)
        db_session.commit()

        result: AnomalyDetectionResult = run_anomaly_detection_for_asset(
            sample_asset, db_session, lookback_days=5, persist=False
        )
        assert result.anomalies_detected == 0
        assert isinstance(result, AnomalyDetectionResult)

    def test_spike_produces_anomaly(self, db_session, sample_asset, sample_component):
        """Data with a 10-sigma spike → at least one anomaly detected."""
        readings = _make_readings_with_spike(
            str(sample_asset.id), str(sample_component.id), n=60, spike_value=500.0, spike_index=55
        )
        db_session.add_all(readings)
        db_session.commit()

        result: AnomalyDetectionResult = run_anomaly_detection_for_asset(
            sample_asset, db_session, lookback_days=5, persist=False
        )
        assert result.anomalies_detected >= 1

    def test_result_has_expected_fields(self, db_session, sample_asset, sample_component):
        """Result object has all expected fields."""
        result: AnomalyDetectionResult = run_anomaly_detection_for_asset(
            sample_asset, db_session, lookback_days=5, persist=False
        )
        assert hasattr(result, "asset_id")
        assert hasattr(result, "total_readings_checked")
        assert hasattr(result, "anomalies_detected")
        assert hasattr(result, "by_severity")
        assert hasattr(result, "by_sensor_type")
        assert hasattr(result, "errors")

    def test_insufficient_readings_returns_zero(self, db_session, sample_asset, sample_component):
        """Fewer readings than MIN_READINGS_FOR_DETECTION → zero anomalies."""
        # Add only 5 readings
        readings = _make_clean_readings(
            str(sample_asset.id), str(sample_component.id), n=5
        )
        db_session.add_all(readings)
        db_session.commit()

        result: AnomalyDetectionResult = run_anomaly_detection_for_asset(
            sample_asset, db_session, lookback_days=5, persist=False
        )
        assert result.anomalies_detected == 0

    def test_persist_false_no_db_writes(self, db_session, sample_asset, sample_component):
        """With persist=False, no AnomalyEvent rows are written to DB."""
        from app.models.models import AnomalyEvent
        readings = _make_readings_with_spike(
            str(sample_asset.id), str(sample_component.id), n=60, spike_value=500.0
        )
        db_session.add_all(readings)
        db_session.commit()

        count_before = db_session.query(AnomalyEvent).count()
        run_anomaly_detection_for_asset(
            sample_asset, db_session, lookback_days=5, persist=False
        )
        count_after = db_session.query(AnomalyEvent).count()
        assert count_before == count_after

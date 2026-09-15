"""
Tests for Phase 5 — Data Quality Engine
==========================================
Tests quality metric computation, INSUFFICIENT_DATA state, and
overall score calculations using synthetic in-memory data.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.analytics.data_quality import (
    compute_asset_data_quality,
    QualityMetrics,
    MIN_READINGS_FOR_ASSESSMENT,
)
from app.models.models import DataQualityLevel, SensorReading


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_reading(
    asset_id: str,
    component_id: str,
    sensor_type: str = "temperature",
    sensor_value: float = 80.0,
    quality_flag: str = "OK",
    ts_offset_hours: int = 0,
) -> SensorReading:
    ts = datetime.now(timezone.utc) - timedelta(hours=ts_offset_hours)
    return SensorReading(
        id=str(uuid.uuid4()),
        asset_id=asset_id,
        component_id=component_id,
        timestamp=ts,
        sensor_type=sensor_type,
        sensor_value=sensor_value,
        unit="C",
        quality_flag=quality_flag,
        ingestion_batch_id="test_batch",
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestDataQualityEngine:
    def test_insufficient_data_when_too_few_readings(self, db_session, sample_asset, sample_component):
        """Less than MIN_READINGS_FOR_ASSESSMENT readings → INSUFFICIENT quality level."""
        # Add only 3 readings (below threshold)
        for i in range(3):
            reading = _make_reading(
                str(sample_asset.id),
                str(sample_component.id),
                ts_offset_hours=i,
            )
            db_session.add(reading)
        db_session.commit()

        metrics = compute_asset_data_quality(sample_asset, db_session, window_days=30)
        assert metrics.quality_level == DataQualityLevel.INSUFFICIENT
        assert metrics.overall_score == 0.0
        assert metrics.total_records == 3

    def test_good_quality_with_clean_data(self, db_session, sample_asset, sample_component):
        """All-OK readings with recent timestamps → HIGH or GOOD quality."""
        for i in range(MIN_READINGS_FOR_ASSESSMENT + 5):
            reading = _make_reading(
                str(sample_asset.id),
                str(sample_component.id),
                ts_offset_hours=i * 2,
            )
            db_session.add(reading)
        db_session.commit()

        metrics = compute_asset_data_quality(sample_asset, db_session, window_days=30)
        assert metrics.quality_level in (DataQualityLevel.EXCELLENT, DataQualityLevel.GOOD)
        assert metrics.overall_score > 0.5
        assert metrics.total_records >= MIN_READINGS_FOR_ASSESSMENT

    def test_outlier_rate_increases_with_outlier_flags(self, db_session, sample_asset, sample_component):
        """Adding OUTLIER-flagged readings increases the outlier_rate metric."""
        # 10 good readings
        for i in range(10):
            db_session.add(_make_reading(
                str(sample_asset.id), str(sample_component.id), ts_offset_hours=i * 2,
            ))
        # 5 outlier readings
        for i in range(5):
            db_session.add(_make_reading(
                str(sample_asset.id), str(sample_component.id),
                ts_offset_hours=20 + i * 2, quality_flag="OUTLIER",
            ))
        db_session.commit()

        metrics = compute_asset_data_quality(sample_asset, db_session, window_days=30)
        assert metrics.outlier_rate > 0.0

    def test_quality_metrics_fields_in_range(self, db_session, sample_asset, sample_component):
        """All metric values are in [0.0, 1.0] range."""
        for i in range(MIN_READINGS_FOR_ASSESSMENT + 2):
            db_session.add(_make_reading(
                str(sample_asset.id), str(sample_component.id), ts_offset_hours=i,
            ))
        db_session.commit()

        m = compute_asset_data_quality(sample_asset, db_session, window_days=30)
        for field_name in ("completeness", "validity", "consistency", "timeliness",
                           "duplicate_rate", "missing_value_rate", "outlier_rate", "overall_score"):
            val = getattr(m, field_name)
            assert 0.0 <= val <= 1.0, f"{field_name} = {val} is out of [0,1]"

    def test_no_recent_readings_gives_low_timeliness(self, db_session, sample_asset, sample_component):
        """Readings all older than timeliness window → timeliness close to 0."""
        # Insert readings that are 10 days old (outside 3-day timeliness window)
        for i in range(MIN_READINGS_FOR_ASSESSMENT):
            ts = datetime.now(timezone.utc) - timedelta(days=10 + i)
            reading = SensorReading(
                id=str(uuid.uuid4()),
                asset_id=str(sample_asset.id),
                component_id=str(sample_component.id),
                timestamp=ts,
                sensor_type="temperature",
                sensor_value=80.0,
                unit="C",
                quality_flag="OK",
                ingestion_batch_id="test_batch_old",
            )
            db_session.add(reading)
        db_session.commit()

        metrics = compute_asset_data_quality(sample_asset, db_session, window_days=30)
        assert metrics.timeliness < 0.5

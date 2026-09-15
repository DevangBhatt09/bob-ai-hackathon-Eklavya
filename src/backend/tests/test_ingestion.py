"""
Tests for Phase 4 — CSV Ingestion Service
==========================================
Tests validation, happy-path ingestion, and duplicate detection.
Uses SQLite in-memory via the shared conftest fixtures.
"""
import io
import uuid
from datetime import datetime, timezone

import pytest

from app.ingestion.csv_ingestion import (
    IngestionResult,
    ingest_sensor_csv,
    ingest_maintenance_csv,
    SENSOR_REQUIRED_COLUMNS,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _csv(rows: list[str]) -> bytes:
    """Join header + rows into UTF-8 bytes."""
    return "\n".join(rows).encode("utf-8")


SENSOR_HEADER = "timestamp,asset_id,component_id,sensor_type,sensor_value,unit,quality_flag"
MAINT_HEADER = "maintenance_id,asset_id,component_id,maintenance_date,maintenance_type,description,technician,operating_hours,outcome"


# ─── Sensor CSV tests ─────────────────────────────────────────────────────────

class TestSensorCSVIngestion:
    def test_happy_path_inserts_rows(self, db_session, sample_asset, sample_component):
        """Valid CSV with a single row inserts one SensorReading."""
        ts = "2026-01-01T12:00:00+00:00"
        csv_bytes = _csv([
            SENSOR_HEADER,
            f"{ts},{sample_asset.asset_id},{sample_component.component_id},temperature,85.5,C,OK",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.valid_rows == 1
        assert result.invalid_rows == 0
        assert len(result.errors) == 0

    def test_missing_required_column_rejected(self, db_session):
        """CSV missing 'sensor_value' column is rejected with schema error."""
        csv_bytes = _csv([
            "timestamp,asset_id,sensor_type",
            "2026-01-01T12:00:00+00:00,GR-1001,temperature",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.valid_rows == 0
        assert not result.schema_ok

    def test_invalid_timestamp_row_rejected(self, db_session, sample_asset, sample_component):
        """Row with malformed timestamp is rejected, others pass."""
        ts_good = "2026-01-01T12:00:00+00:00"
        ts_bad  = "not-a-date"
        csv_bytes = _csv([
            SENSOR_HEADER,
            f"{ts_good},{sample_asset.asset_id},{sample_component.component_id},temperature,85.5,C,OK",
            f"{ts_bad},{sample_asset.asset_id},{sample_component.component_id},temperature,90.0,C,OK",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.valid_rows == 1
        assert result.invalid_rows == 1

    def test_out_of_range_sensor_value_flagged(self, db_session, sample_asset, sample_component):
        """Sensor value outside allowed range is rejected."""
        ts = "2026-01-01T12:00:00+00:00"
        # temperature > 300.0 — out of range
        csv_bytes = _csv([
            SENSOR_HEADER,
            f"{ts},{sample_asset.asset_id},{sample_component.component_id},temperature,9999.0,C,OK",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.invalid_rows == 1

    def test_unknown_asset_id_row_rejected(self, db_session):
        """Row referencing a non-existent asset_id is rejected."""
        ts = "2026-01-01T12:00:00+00:00"
        csv_bytes = _csv([
            SENSOR_HEADER,
            f"{ts},NONEXISTENT-999,,temperature,85.5,C,OK",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.invalid_rows == 1

    def test_intra_batch_duplicate_rejected(self, db_session, sample_asset, sample_component):
        """Duplicate rows within the same CSV batch are rejected."""
        ts = "2026-01-02T12:00:00+00:00"
        row = f"{ts},{sample_asset.asset_id},{sample_component.component_id},temperature,85.5,C,OK"
        csv_bytes = _csv([SENSOR_HEADER, row, row])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.valid_rows == 1
        assert result.duplicate_rows == 1

    def test_empty_csv_returns_zero_counts(self, db_session):
        """Empty CSV (header only) produces zero accepted/rejected rows."""
        csv_bytes = _csv([SENSOR_HEADER])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.valid_rows == 0
        assert result.invalid_rows == 0

    def test_invalid_sensor_type_rejected(self, db_session, sample_asset, sample_component):
        """Unknown sensor type is rejected."""
        ts = "2026-01-03T12:00:00+00:00"
        csv_bytes = _csv([
            SENSOR_HEADER,
            f"{ts},{sample_asset.asset_id},{sample_component.component_id},UNKNOWN_TYPE,85.5,C,OK",
        ])
        result: IngestionResult = ingest_sensor_csv(csv_bytes, "test.csv", db_session)
        assert result.invalid_rows == 1


# ─── Maintenance CSV tests ────────────────────────────────────────────────────

class TestMaintenanceCSVIngestion:
    def test_happy_path_inserts_row(self, db_session, sample_asset, sample_component):
        """Valid maintenance CSV row inserts one MaintenanceRecord."""
        ts = "2026-01-05T08:00:00+00:00"
        csv_bytes = _csv([
            MAINT_HEADER,
            f"M-TEST-001,{sample_asset.asset_id},{sample_component.component_id},{ts},SCHEDULED,Oil change,Tech. Smith,500.0,COMPLETED",
        ])
        result: IngestionResult = ingest_maintenance_csv(csv_bytes, "maint.csv", db_session)
        assert result.valid_rows == 1
        assert result.invalid_rows == 0

    def test_invalid_maintenance_type_rejected(self, db_session, sample_asset, sample_component):
        """Row with invalid maintenance_type is rejected."""
        ts = "2026-01-05T08:00:00+00:00"
        csv_bytes = _csv([
            MAINT_HEADER,
            f"M-TEST-002,{sample_asset.asset_id},{sample_component.component_id},{ts},FAKETYPE,Oil change,Tech. Smith,500.0,COMPLETED",
        ])
        result: IngestionResult = ingest_maintenance_csv(csv_bytes, "maint.csv", db_session)
        assert result.invalid_rows == 1

    def test_missing_required_column_rejected(self, db_session):
        """CSV missing maintenance_type column is rejected."""
        csv_bytes = _csv([
            "maintenance_id,asset_id,maintenance_date",
            "M-TEST-003,GR-1001,2026-01-05",
        ])
        result: IngestionResult = ingest_maintenance_csv(csv_bytes, "maint.csv", db_session)
        assert result.valid_rows == 0
        assert not result.schema_ok

    def test_result_has_filename(self, db_session, sample_asset, sample_component):
        """IngestionResult carries the given filename."""
        ts = "2026-01-06T08:00:00+00:00"
        csv_bytes = _csv([
            MAINT_HEADER,
            f"M-TEST-004,{sample_asset.asset_id},{sample_component.component_id},{ts},INSPECTION,Check,Tech. Smith,600.0,COMPLETED",
        ])
        result: IngestionResult = ingest_maintenance_csv(csv_bytes, "maint.csv", db_session)
        assert result.filename == "maint.csv"

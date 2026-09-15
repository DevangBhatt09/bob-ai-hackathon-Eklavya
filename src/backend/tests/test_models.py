"""
Tests for SQLAlchemy ORM models.
Validates model structure, constraints, and relationships.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.models import (
    Asset,
    AssetType,
    Component,
    MaintenanceRecord,
    MaintenanceType,
    SensorReading,
    ReadinessStatus,
    RiskCategory,
    AnomalySeverity,
    AnomalyType,
)


class TestAssetModel:
    def test_create_asset(self, db_session, sample_asset):
        """Asset can be created and persisted."""
        assert sample_asset.id is not None
        assert sample_asset.asset_id.startswith("TEST-")
        assert sample_asset.asset_type == AssetType.ROTARY_WING
        assert sample_asset.total_operating_hours == 1250.5

    def test_asset_unique_asset_id(self, db_session, sample_asset):
        """Duplicate asset_id raises integrity error."""
        from sqlalchemy.exc import IntegrityError
        dup = Asset(
            id=str(uuid.uuid4()),
            asset_id=sample_asset.asset_id,  # duplicate of the fixture's unique ID
            name="Duplicate",
            asset_type=AssetType.FIXED_WING,
            total_operating_hours=0.0,
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_asset_has_timestamps(self, db_session, sample_asset):
        """Asset has created_at and updated_at timestamps."""
        refreshed = db_session.query(Asset).filter_by(asset_id=sample_asset.asset_id).first()
        assert refreshed is not None
        assert refreshed.created_at is not None


class TestComponentModel:
    def test_create_component(self, db_session, sample_component):
        """Component can be created with proper FK relationship."""
        assert sample_component.id is not None
        assert sample_component.component_id == "TEST-A001-ENG"
        assert sample_component.criticality == "HIGH"

    def test_component_asset_relationship(self, db_session, sample_asset, sample_component):
        """Component relates back to its asset."""
        db_session.refresh(sample_asset)
        assert len(sample_asset.components) == 1
        assert sample_asset.components[0].component_id == "TEST-A001-ENG"

    def test_component_unique_per_asset(self, db_session, sample_asset, sample_component):
        """Duplicate component_id per asset raises integrity error."""
        from sqlalchemy.exc import IntegrityError
        dup = Component(
            id=str(uuid.uuid4()),
            asset_id=sample_asset.id,
            component_id="TEST-A001-ENG",  # duplicate
            name="Another Engine",
            component_type="engine",
            criticality="HIGH",
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestSensorReadingModel:
    def test_create_sensor_reading(self, db_session, sample_asset, sample_component):
        """SensorReading can be created and persisted."""
        reading = SensorReading(
            id=str(uuid.uuid4()),
            asset_id=sample_asset.id,
            component_id=sample_component.id,
            timestamp=datetime.now(timezone.utc),
            sensor_type="temperature",
            sensor_value=87.3,
            unit="°C",
            quality_flag="OK",
        )
        db_session.add(reading)
        db_session.commit()
        assert reading.id is not None
        assert reading.sensor_value == 87.3

    def test_sensor_reading_belongs_to_asset(self, db_session, sample_asset, sample_component):
        """SensorReading FK to asset works."""
        reading = SensorReading(
            id=str(uuid.uuid4()),
            asset_id=sample_asset.id,
            component_id=sample_component.id,
            timestamp=datetime.now(timezone.utc),
            sensor_type="vibration",
            sensor_value=2.8,
            unit="mm/s",
        )
        db_session.add(reading)
        db_session.commit()
        db_session.refresh(sample_asset)
        assert any(r.sensor_type == "vibration" for r in sample_asset.sensor_readings)


class TestMaintenanceRecordModel:
    def test_create_maintenance_record(self, db_session, sample_asset, sample_component):
        """MaintenanceRecord can be created with all required fields."""
        record = MaintenanceRecord(
            id=str(uuid.uuid4()),
            maintenance_event_id="M-TEST-A001-SCH-0001",
            asset_id=sample_asset.id,
            component_id=sample_component.id,
            maintenance_date=datetime.now(timezone.utc),
            maintenance_type=MaintenanceType.SCHEDULED,
            description="Scheduled inspection",
            technician="Sgt. Test",
            operating_hours_at_maintenance=1200.0,
            outcome="COMPLETED",
        )
        db_session.add(record)
        db_session.commit()
        assert record.id is not None
        assert record.maintenance_type == MaintenanceType.SCHEDULED

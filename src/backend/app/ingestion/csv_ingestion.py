"""
CSV Ingestion Service
=====================
Validates and ingests sensor / maintenance CSV uploads into PostgreSQL.

Rules:
- All validation errors are reported, not silently discarded.
- Invalid rows are rejected; valid rows are committed in a single transaction.
- Duplicate detection is per-batch (same asset+component+timestamp+sensor_type).
- Existing DB rows are NOT overwritten; duplicates against DB produce warnings.
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset, Component, MaintenanceRecord, MaintenanceType, SensorReading

logger = logging.getLogger(__name__)

# ── Column schemas ─────────────────────────────────────────────────────────────

SENSOR_REQUIRED_COLUMNS = {"timestamp", "asset_id", "sensor_type", "sensor_value"}
SENSOR_OPTIONAL_COLUMNS = {"component_id", "unit", "quality_flag"}

MAINTENANCE_REQUIRED_COLUMNS = {
    "maintenance_id", "asset_id", "maintenance_date", "maintenance_type"
}
MAINTENANCE_OPTIONAL_COLUMNS = {
    "component_id", "description", "technician", "operating_hours", "outcome"
}

# Accepted sensor types
VALID_SENSOR_TYPES = {
    "temperature", "vibration", "pressure", "rpm", "voltage",
    "current", "fluid_level", "operating_hours", "cycle_count",
}

# Sensor value ranges (inclusive) for range validation
SENSOR_RANGES: dict[str, tuple[float, float]] = {
    "temperature": (-50.0, 300.0),
    "vibration": (0.0, 100.0),
    "pressure": (0.0, 500.0),
    "rpm": (0.0, 15000.0),
    "voltage": (0.0, 1000.0),
    "current": (0.0, 1000.0),
    "fluid_level": (0.0, 100.0),
    "operating_hours": (0.0, 100000.0),
    "cycle_count": (0.0, 1_000_000.0),
}

VALID_MAINTENANCE_TYPES = {m.value for m in MaintenanceType}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class RowError:
    row_number: int
    field: str
    message: str
    raw_value: Any = None


@dataclass
class IngestionResult:
    filename: str
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    missing_value_rows: int = 0
    persisted: int = 0
    errors: list[RowError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_ok: bool = True
    missing_columns: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.schema_ok and self.persisted > 0

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "duplicate_rows": self.duplicate_rows,
            "missing_value_rows": self.missing_value_rows,
            "persisted": self.persisted,
            "schema_ok": self.schema_ok,
            "missing_columns": self.missing_columns,
            "error_count": len(self.errors),
            "errors": [
                {"row": e.row_number, "field": e.field, "message": e.message, "value": str(e.raw_value)}
                for e in self.errors[:50]  # cap at 50 for API response
            ],
            "warnings": self.warnings[:20],
        }


# ── Sensor CSV ingestion ──────────────────────────────────────────────────────

def ingest_sensor_csv(
    content: bytes,
    filename: str,
    db: Session,
    batch_id: str | None = None,
) -> IngestionResult:
    """
    Parse, validate, and persist a sensor readings CSV.

    Returns an IngestionResult with full validation details.
    Does NOT silently discard rows — all errors are reported.
    """
    result = IngestionResult(filename=filename)
    if batch_id is None:
        batch_id = f"upload_{uuid.uuid4().hex[:12]}"

    # ── Parse CSV ────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str, low_memory=False)
    except Exception as e:
        result.schema_ok = False
        result.errors.append(RowError(0, "file", f"CSV parse error: {e}"))
        return result

    df.columns = [c.strip().lower() for c in df.columns]
    result.total_rows = len(df)

    # ── Schema validation ────────────────────────────────────────────────────
    missing = SENSOR_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        result.schema_ok = False
        result.missing_columns = sorted(missing)
        result.errors.append(RowError(0, "schema", f"Missing required columns: {sorted(missing)}"))
        return result

    # ── Pre-load known assets and components ─────────────────────────────────
    known_assets: dict[str, Asset] = {
        a.asset_id: a for a in db.query(Asset).filter(Asset.is_active == True).all()
    }
    known_components: dict[str, Component] = {
        c.component_id: c for c in db.query(Component).all()
    }

    # ── Per-row validation ────────────────────────────────────────────────────
    readings_to_insert: list[SensorReading] = []
    seen_keys: set[tuple] = set()  # dedup within this batch

    for i, row in df.iterrows():
        row_num = int(i) + 2  # 1-based + header row
        errors_in_row: list[RowError] = []

        # timestamp
        ts_raw = _strip(row.get("timestamp"))
        timestamp = None
        if not ts_raw:
            errors_in_row.append(RowError(row_num, "timestamp", "Missing timestamp"))
            result.missing_value_rows += 1
        else:
            timestamp = _parse_timestamp(ts_raw)
            if timestamp is None:
                errors_in_row.append(RowError(row_num, "timestamp", f"Invalid timestamp format: {ts_raw!r}", ts_raw))

        # asset_id
        asset_id_str = _strip(row.get("asset_id"))
        asset_obj = None
        if not asset_id_str:
            errors_in_row.append(RowError(row_num, "asset_id", "Missing asset_id"))
            result.missing_value_rows += 1
        else:
            asset_obj = known_assets.get(asset_id_str)
            if asset_obj is None:
                errors_in_row.append(RowError(row_num, "asset_id", f"Unknown asset_id: {asset_id_str!r}", asset_id_str))

        # sensor_type
        sensor_type = _strip(row.get("sensor_type", "")).lower()
        if not sensor_type:
            errors_in_row.append(RowError(row_num, "sensor_type", "Missing sensor_type"))
            result.missing_value_rows += 1
        elif sensor_type not in VALID_SENSOR_TYPES:
            errors_in_row.append(RowError(row_num, "sensor_type", f"Invalid sensor_type: {sensor_type!r}", sensor_type))

        # sensor_value
        value_raw = _strip(row.get("sensor_value"))
        sensor_value = None
        if value_raw is None or value_raw == "":
            errors_in_row.append(RowError(row_num, "sensor_value", "Missing sensor_value"))
            result.missing_value_rows += 1
        else:
            try:
                sensor_value = float(value_raw)
            except ValueError:
                errors_in_row.append(RowError(row_num, "sensor_value", f"Non-numeric sensor_value: {value_raw!r}", value_raw))

        # range validation
        if sensor_value is not None and sensor_type in SENSOR_RANGES:
            lo, hi = SENSOR_RANGES[sensor_type]
            if not (lo <= sensor_value <= hi):
                errors_in_row.append(RowError(row_num, "sensor_value",
                    f"sensor_value {sensor_value} out of range [{lo}, {hi}] for {sensor_type}", sensor_value))

        # optional: component_id
        comp_id_str = _strip(row.get("component_id"))
        component_obj = None
        if comp_id_str:
            component_obj = known_components.get(comp_id_str)
            if component_obj is None:
                result.warnings.append(f"Row {row_num}: unknown component_id {comp_id_str!r}, will store without component link")

        # optional fields
        unit = _strip(row.get("unit"))
        quality_flag = _strip(row.get("quality_flag")) or "OK"

        # accumulate row errors
        if errors_in_row:
            result.errors.extend(errors_in_row)
            result.invalid_rows += 1
            continue

        # dedup within batch
        dedup_key = (asset_obj.id, component_obj.id if component_obj else None, timestamp, sensor_type)
        if dedup_key in seen_keys:
            result.duplicate_rows += 1
            result.warnings.append(f"Row {row_num}: duplicate reading (same asset/component/timestamp/sensor_type), skipped")
            continue
        seen_keys.add(dedup_key)

        result.valid_rows += 1
        readings_to_insert.append(SensorReading(
            id=uuid.uuid4(),
            asset_id=asset_obj.id,
            component_id=component_obj.id if component_obj else None,
            timestamp=timestamp,
            sensor_type=sensor_type,
            sensor_value=sensor_value,
            unit=unit,
            quality_flag=quality_flag,
            ingestion_batch_id=batch_id,
        ))

    # ── Persist valid rows in one transaction ─────────────────────────────────
    if readings_to_insert:
        try:
            db.bulk_save_objects(readings_to_insert)
            db.commit()
            result.persisted = len(readings_to_insert)
            logger.info("Ingested %d sensor readings from %s (batch %s)", result.persisted, filename, batch_id)
        except Exception as e:
            db.rollback()
            result.errors.append(RowError(0, "database", f"Database commit failed: {e}"))
            result.persisted = 0
            logger.error("Sensor ingestion failed for %s: %s", filename, e)

    return result


# ── Maintenance CSV ingestion ─────────────────────────────────────────────────

def ingest_maintenance_csv(
    content: bytes,
    filename: str,
    db: Session,
    batch_id: str | None = None,
) -> IngestionResult:
    """
    Parse, validate, and persist maintenance records CSV.
    """
    result = IngestionResult(filename=filename)
    if batch_id is None:
        batch_id = f"maint_upload_{uuid.uuid4().hex[:12]}"

    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str, low_memory=False)
    except Exception as e:
        result.schema_ok = False
        result.errors.append(RowError(0, "file", f"CSV parse error: {e}"))
        return result

    df.columns = [c.strip().lower() for c in df.columns]
    result.total_rows = len(df)

    missing = MAINTENANCE_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        result.schema_ok = False
        result.missing_columns = sorted(missing)
        result.errors.append(RowError(0, "schema", f"Missing required columns: {sorted(missing)}"))
        return result

    known_assets: dict[str, Asset] = {
        a.asset_id: a for a in db.query(Asset).filter(Asset.is_active == True).all()
    }
    known_components: dict[str, Component] = {
        c.component_id: c for c in db.query(Component).all()
    }

    # Existing maintenance event IDs (for duplicate check)
    existing_event_ids: set[str] = {
        row[0] for row in db.query(MaintenanceRecord.maintenance_event_id).all()
    }

    records_to_insert: list[MaintenanceRecord] = []
    seen_event_ids: set[str] = set()

    for i, row in df.iterrows():
        row_num = int(i) + 2
        errors_in_row: list[RowError] = []

        # maintenance_id
        event_id = _strip(row.get("maintenance_id"))
        if not event_id:
            errors_in_row.append(RowError(row_num, "maintenance_id", "Missing maintenance_id"))
            result.missing_value_rows += 1
        elif event_id in existing_event_ids:
            result.duplicate_rows += 1
            result.warnings.append(f"Row {row_num}: maintenance_id {event_id!r} already exists in DB, skipped")
            continue
        elif event_id in seen_event_ids:
            result.duplicate_rows += 1
            result.warnings.append(f"Row {row_num}: duplicate maintenance_id {event_id!r} in this file, skipped")
            continue
        else:
            seen_event_ids.add(event_id)

        # asset_id
        asset_id_str = _strip(row.get("asset_id"))
        asset_obj = None
        if not asset_id_str:
            errors_in_row.append(RowError(row_num, "asset_id", "Missing asset_id"))
            result.missing_value_rows += 1
        else:
            asset_obj = known_assets.get(asset_id_str)
            if asset_obj is None:
                errors_in_row.append(RowError(row_num, "asset_id", f"Unknown asset_id: {asset_id_str!r}", asset_id_str))

        # maintenance_date
        date_raw = _strip(row.get("maintenance_date"))
        maint_date = None
        if not date_raw:
            errors_in_row.append(RowError(row_num, "maintenance_date", "Missing maintenance_date"))
            result.missing_value_rows += 1
        else:
            maint_date = _parse_timestamp(date_raw)
            if maint_date is None:
                errors_in_row.append(RowError(row_num, "maintenance_date", f"Invalid date: {date_raw!r}", date_raw))

        # maintenance_type
        maint_type_raw = _strip(row.get("maintenance_type", "")).upper()
        if not maint_type_raw:
            errors_in_row.append(RowError(row_num, "maintenance_type", "Missing maintenance_type"))
            result.missing_value_rows += 1
        elif maint_type_raw not in VALID_MAINTENANCE_TYPES:
            errors_in_row.append(RowError(row_num, "maintenance_type",
                f"Invalid maintenance_type {maint_type_raw!r}. Valid: {sorted(VALID_MAINTENANCE_TYPES)}", maint_type_raw))

        if errors_in_row:
            result.errors.extend(errors_in_row)
            result.invalid_rows += 1
            continue

        # optional fields
        comp_id_str = _strip(row.get("component_id"))
        component_obj = known_components.get(comp_id_str) if comp_id_str else None
        if comp_id_str and component_obj is None:
            result.warnings.append(f"Row {row_num}: unknown component_id {comp_id_str!r}, storing without link")

        op_hours_raw = _strip(row.get("operating_hours"))
        op_hours = None
        if op_hours_raw:
            try:
                op_hours = float(op_hours_raw)
                if op_hours < 0:
                    result.warnings.append(f"Row {row_num}: negative operating_hours {op_hours}")
                    op_hours = None
            except ValueError:
                result.warnings.append(f"Row {row_num}: non-numeric operating_hours {op_hours_raw!r}")

        result.valid_rows += 1
        records_to_insert.append(MaintenanceRecord(
            id=uuid.uuid4(),
            maintenance_event_id=event_id,
            asset_id=asset_obj.id,
            component_id=component_obj.id if component_obj else None,
            maintenance_date=maint_date,
            maintenance_type=MaintenanceType(maint_type_raw),
            description=_strip(row.get("description")),
            technician=_strip(row.get("technician")),
            operating_hours_at_maintenance=op_hours,
            outcome=_strip(row.get("outcome")),
        ))

    if records_to_insert:
        try:
            db.bulk_save_objects(records_to_insert)
            db.commit()
            result.persisted = len(records_to_insert)
            logger.info("Ingested %d maintenance records from %s", result.persisted, filename)
        except Exception as e:
            db.rollback()
            result.errors.append(RowError(0, "database", f"Database commit failed: {e}"))
            result.persisted = 0
            logger.error("Maintenance ingestion failed for %s: %s", filename, e)

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip(val: Any) -> str | None:
    """Strip whitespace and return None for empty/NaN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "null", "") else None


def _parse_timestamp(s: str) -> datetime | None:
    """Try multiple common timestamp formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Try pandas as fallback
    try:
        dt = pd.Timestamp(s).to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

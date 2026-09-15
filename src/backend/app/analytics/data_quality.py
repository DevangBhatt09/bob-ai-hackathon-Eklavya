"""
Data Quality Engine
====================
Computes real data-quality metrics for each asset's sensor readings.

Metrics:
- completeness  : fraction of expected readings that actually exist
- validity      : fraction of readings passing range/type checks
- consistency   : absence of duplicate records
- timeliness    : recency of the most recent reading
- duplicate_rate: fraction of records that are duplicates
- missing_value_rate: fraction of readings where sensor_value is NULL or flagged
- outlier_rate  : fraction of readings flagged as outliers (OUTLIER/RANGE_VIOLATION)
- overall_score : weighted average of the above

Critical rule: INSUFFICIENT DATA is an explicit, distinct quality state.
Missing data NEVER implies a healthy asset.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import numpy as np
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.models import (
    Asset,
    DataQualityLevel,
    DataQualityReport,
    SensorReading,
)

logger = logging.getLogger(__name__)

# Minimum readings needed to give a meaningful quality score
MIN_READINGS_FOR_ASSESSMENT = 10
# Expected readings per day per component (used for completeness estimation)
EXPECTED_READINGS_PER_DAY = 4.0
# How old (days) can the most recent reading be and still be "timely"
TIMELINESS_WINDOW_DAYS = 3.0
# Outlier quality flags
OUTLIER_FLAGS = {"OUTLIER", "RANGE_VIOLATION"}
DUPLICATE_FLAGS = {"DUPLICATE"}


class QualityMetrics(NamedTuple):
    completeness: float
    validity: float
    consistency: float
    timeliness: float
    duplicate_rate: float
    missing_value_rate: float
    outlier_rate: float
    overall_score: float
    quality_level: DataQualityLevel
    total_records: int
    issues_detail: dict


def compute_asset_data_quality(
    asset: Asset,
    db: Session,
    window_days: int = 30,
) -> QualityMetrics:
    """
    Compute data quality metrics for a single asset over the past `window_days`.

    Returns INSUFFICIENT_DATA state if fewer than MIN_READINGS_FOR_ASSESSMENT
    readings exist — never treats absence of data as healthy.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)

    # ── Fetch readings in window ───────────────────────────────────────────────
    readings_q = (
        db.query(SensorReading)
        .filter(
            SensorReading.asset_id == asset.id,
            SensorReading.timestamp >= window_start,
        )
    )
    total_records = readings_q.count()

    if total_records < MIN_READINGS_FOR_ASSESSMENT:
        return QualityMetrics(
            completeness=0.0,
            validity=0.0,
            consistency=0.0,
            timeliness=0.0,
            duplicate_rate=0.0,
            missing_value_rate=1.0,
            outlier_rate=0.0,
            overall_score=0.0,
            quality_level=DataQualityLevel.INSUFFICIENT,
            total_records=total_records,
            issues_detail={
                "reason": "insufficient_data",
                "total_records": total_records,
                "min_required": MIN_READINGS_FOR_ASSESSMENT,
                "window_days": window_days,
                "note": "Missing data does not imply healthy asset condition.",
            },
        )

    # Load all readings for analysis
    readings = readings_q.all()
    quality_flags = [r.quality_flag or "OK" for r in readings]
    flag_counts: dict[str, int] = {}
    for f in quality_flags:
        flag_counts[f] = flag_counts.get(f, 0) + 1

    # ── Completeness ──────────────────────────────────────────────────────────
    # Estimate expected readings: n_components * n_sensor_types * days * rate
    from app.models.models import Component as _Component
    n_components = (
        db.query(func.count(_Component.id.distinct()))
        .filter(_Component.asset_id == asset.id)
        .scalar() or 1
    )
    avg_sensors = (
        db.query(func.count(SensorReading.sensor_type.distinct()))
        .filter(SensorReading.asset_id == asset.id)
        .scalar() or 1
    )
    expected_readings = n_components * avg_sensors * window_days * EXPECTED_READINGS_PER_DAY
    # Missing-gap readings are counted as missing (not in DB at all)
    # We compare actual to expected
    completeness = min(1.0, total_records / max(1, expected_readings))

    # ── Missing value rate ────────────────────────────────────────────────────
    # A reading is "missing" if quality_flag indicates a skipped/null reading
    # We also count readings with sensor_value that are NaN
    null_values = sum(1 for r in readings if r.sensor_value is None)
    missing_flagged = flag_counts.get("MISSING", 0) + flag_counts.get("NULL", 0)
    missing_value_rate = (null_values + missing_flagged) / max(1, total_records)

    # ── Validity ──────────────────────────────────────────────────────────────
    # Invalid = RANGE_VIOLATION or sensor_value is None
    invalid_count = flag_counts.get("RANGE_VIOLATION", 0) + null_values
    validity = 1.0 - (invalid_count / max(1, total_records))
    validity = max(0.0, validity)

    # ── Consistency (duplicate rate) ──────────────────────────────────────────
    duplicate_count = sum(flag_counts.get(f, 0) for f in DUPLICATE_FLAGS)
    duplicate_rate = duplicate_count / max(1, total_records)
    consistency = 1.0 - duplicate_rate

    # ── Outlier rate ──────────────────────────────────────────────────────────
    outlier_count = sum(flag_counts.get(f, 0) for f in OUTLIER_FLAGS)
    outlier_rate = outlier_count / max(1, total_records)

    # ── Timeliness ────────────────────────────────────────────────────────────
    latest_reading = max((r.timestamp for r in readings), default=None)
    if latest_reading is None:
        timeliness = 0.0
    else:
        if latest_reading.tzinfo is None:
            latest_reading = latest_reading.replace(tzinfo=timezone.utc)
        age_days = (now - latest_reading).total_seconds() / 86400.0
        timeliness = max(0.0, 1.0 - (age_days / TIMELINESS_WINDOW_DAYS))

    # ── Overall score (weighted) ──────────────────────────────────────────────
    weights = {
        "completeness": 0.25,
        "validity": 0.25,
        "consistency": 0.15,
        "timeliness": 0.15,
        "missing_value": 0.10,  # penalizes (1 - missing_rate)
        "outlier": 0.10,        # penalizes (1 - outlier_rate)
    }
    overall_score = (
        weights["completeness"] * completeness
        + weights["validity"] * validity
        + weights["consistency"] * consistency
        + weights["timeliness"] * timeliness
        + weights["missing_value"] * (1.0 - missing_value_rate)
        + weights["outlier"] * (1.0 - outlier_rate)
    )
    overall_score = round(max(0.0, min(1.0, overall_score)), 4)

    # ── Quality level classification ──────────────────────────────────────────
    quality_level = _classify_quality(overall_score, total_records)

    issues_detail = {
        "total_records": total_records,
        "expected_records_estimated": int(expected_readings),
        "flag_counts": flag_counts,
        "null_values": null_values,
        "duplicate_count": duplicate_count,
        "outlier_count": outlier_count,
        "invalid_count": invalid_count,
        "latest_reading_age_days": round(
            (now - latest_reading).total_seconds() / 86400.0, 2
        ) if latest_reading else None,
        "window_days": window_days,
    }

    return QualityMetrics(
        completeness=round(completeness, 4),
        validity=round(validity, 4),
        consistency=round(consistency, 4),
        timeliness=round(timeliness, 4),
        duplicate_rate=round(duplicate_rate, 4),
        missing_value_rate=round(missing_value_rate, 4),
        outlier_rate=round(outlier_rate, 4),
        overall_score=overall_score,
        quality_level=quality_level,
        total_records=total_records,
        issues_detail=issues_detail,
    )


def _classify_quality(score: float, total_records: int) -> DataQualityLevel:
    """Classify overall quality score into a named level."""
    if total_records < MIN_READINGS_FOR_ASSESSMENT:
        return DataQualityLevel.INSUFFICIENT
    if score >= 0.90:
        return DataQualityLevel.EXCELLENT
    if score >= 0.75:
        return DataQualityLevel.GOOD
    if score >= 0.55:
        return DataQualityLevel.FAIR
    if score >= 0.30:
        return DataQualityLevel.POOR
    return DataQualityLevel.INSUFFICIENT


def run_data_quality_for_all_assets(
    db: Session,
    window_days: int = 30,
    pipeline_run_id: str | None = None,
) -> list[DataQualityReport]:
    """
    Compute and persist data quality reports for all active assets.

    Returns the list of created DataQualityReport records.
    """
    if pipeline_run_id is None:
        pipeline_run_id = f"dq_{uuid.uuid4().hex[:12]}"

    assets = db.query(Asset).filter(Asset.is_active == True).all()
    now = datetime.now(timezone.utc)
    reports: list[DataQualityReport] = []

    for asset in assets:
        metrics = compute_asset_data_quality(asset, db, window_days=window_days)

        report = DataQualityReport(
            id=uuid.uuid4(),
            asset_id=asset.id,
            report_date=now,
            completeness_score=metrics.completeness,
            validity_score=metrics.validity,
            consistency_score=metrics.consistency,
            timeliness_score=metrics.timeliness,
            duplicate_rate=metrics.duplicate_rate,
            missing_value_rate=metrics.missing_value_rate,
            outlier_rate=metrics.outlier_rate,
            overall_score=metrics.overall_score,
            quality_level=metrics.quality_level,
            total_records=metrics.total_records,
            issues_detail=metrics.issues_detail,
            pipeline_run_id=pipeline_run_id,
        )
        db.add(report)
        reports.append(report)

    try:
        db.commit()
        logger.info("Data quality computed for %d assets (run %s)", len(reports), pipeline_run_id)
    except Exception as e:
        db.rollback()
        logger.error("Data quality persist failed: %s", e)
        raise

    return reports

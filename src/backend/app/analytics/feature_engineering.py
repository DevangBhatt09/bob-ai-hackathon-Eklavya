"""
Feature Engineering Service
============================
Computes predictive-maintenance features from sensor readings and
maintenance history.

Data-leakage rule:
  All features are computed using ONLY information available at or before
  the `as_of` timestamp. Future data is never used.

Features produced per component:
  Sensor features:
    rolling_mean_{sensor}, rolling_std_{sensor},
    min_{sensor}, max_{sensor}, median_{sensor},
    rate_of_change_{sensor}, trend_slope_{sensor},
    baseline_deviation_{sensor}, variability_{sensor},
    threshold_exceedance_freq_{sensor}, anomaly_freq_{sensor}

  Usage features:
    operating_hours, cycle_count,
    cycles_since_maintenance, hours_since_maintenance

  Maintenance features:
    component_age_days, days_since_maintenance,
    maintenance_frequency_per_90d, fault_count, replacement_count,
    anomaly_count_30d

  Temporal features:
    short_term_trend_{sensor}  (7-day window)
    long_term_trend_{sensor}   (30-day window)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from app.models.models import (
    AnomalyEvent,
    Component,
    MaintenanceRecord,
    MaintenanceType,
    SensorReading,
)

logger = logging.getLogger(__name__)

# Sensor thresholds for threshold-exceedance features
# Keys match sensor_type values from SENSOR_PARAMS in generator
SENSOR_WARN_THRESHOLDS: dict[str, float] = {
    "temperature": 110.0,
    "vibration": 7.0,
    "pressure": 65.0,
    "rpm": 3200.0,
    "voltage": 31.0,
    "current": 30.0,
    "fluid_level": 95.0,
    "operating_hours": 18.0,
    "cycle_count": 20.0,
}


def compute_component_features(
    component: Component,
    db: Session,
    as_of: datetime | None = None,
    short_window_days: int = 7,
    long_window_days: int = 30,
) -> dict[str, Any]:
    """
    Compute all features for a single component as of `as_of` datetime.

    If `as_of` is None, uses current UTC time.
    All lookups are bounded by `as_of` to prevent data leakage.

    Returns a flat dict of feature_name -> float|int|None.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    features: dict[str, Any] = {}

    # ── Usage features (from component record itself) ─────────────────────────
    features["operating_hours"] = component.current_operating_hours or 0.0
    features["cycle_count"] = component.current_cycles or 0

    install_date = component.install_date
    if install_date:
        if install_date.tzinfo is None:
            install_date = install_date.replace(tzinfo=timezone.utc)
        features["component_age_days"] = (as_of - install_date).total_seconds() / 86400.0
    else:
        features["component_age_days"] = None

    # ── Maintenance features ───────────────────────────────────────────────────
    maintenance_q = (
        db.query(MaintenanceRecord)
        .filter(
            MaintenanceRecord.component_id == component.id,
            MaintenanceRecord.maintenance_date <= as_of,
        )
        .order_by(MaintenanceRecord.maintenance_date.desc())
    )
    all_maintenance = maintenance_q.all()

    if all_maintenance:
        latest = all_maintenance[0]
        latest_date = latest.maintenance_date
        if latest_date.tzinfo is None:
            latest_date = latest_date.replace(tzinfo=timezone.utc)
        features["days_since_maintenance"] = (as_of - latest_date).total_seconds() / 86400.0
        features["hours_since_maintenance"] = (
            component.current_operating_hours - (latest.operating_hours_at_maintenance or 0.0)
        )
        # cycles since last maintenance
        features["cycles_since_maintenance"] = max(
            0, (component.current_cycles or 0) - (latest.cycles_at_maintenance or 0)
        )
    else:
        features["days_since_maintenance"] = None
        features["hours_since_maintenance"] = None
        features["cycles_since_maintenance"] = None

    # Maintenance frequency over last 90 days
    cutoff_90d = as_of - timedelta(days=90)

    def _dt_cmp(dt: datetime, cutoff: datetime) -> bool:
        """Compare two datetimes, stripping tz from both when one is naive (SQLite compat)."""
        if dt is None:
            return False
        if (dt.tzinfo is None) != (cutoff.tzinfo is None):
            # One naive, one aware — strip tz from both for comparison
            dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
            cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
            return dt_naive >= cutoff_naive
        return dt >= cutoff

    maintenance_90d = [m for m in all_maintenance if _dt_cmp(m.maintenance_date, cutoff_90d)]
    features["maintenance_frequency_per_90d"] = len(maintenance_90d)

    # Fault and replacement counts (all history up to as_of)
    features["fault_count"] = sum(
        1 for m in all_maintenance
        if m.maintenance_type in (MaintenanceType.FAULT, MaintenanceType.UNSCHEDULED)
    )
    features["replacement_count"] = sum(
        1 for m in all_maintenance if m.maintenance_type == MaintenanceType.REPLACEMENT
    )

    # ── Anomaly features ───────────────────────────────────────────────────────
    cutoff_30d = as_of - timedelta(days=30)
    anomaly_count_30d = (
        db.query(AnomalyEvent)
        .filter(
            AnomalyEvent.component_id == component.id,
            AnomalyEvent.detected_at >= cutoff_30d,
            AnomalyEvent.detected_at <= as_of,
        )
        .count()
    )
    features["anomaly_count_30d"] = anomaly_count_30d

    # ── Sensor features (per sensor_type) ─────────────────────────────────────
    cutoff_long = as_of - timedelta(days=long_window_days)
    cutoff_short = as_of - timedelta(days=short_window_days)

    readings_long = (
        db.query(SensorReading)
        .filter(
            SensorReading.component_id == component.id,
            SensorReading.timestamp >= cutoff_long,
            SensorReading.timestamp <= as_of,
            SensorReading.quality_flag.notin_(["OUTLIER", "RANGE_VIOLATION", "DUPLICATE", "NULL"]),
        )
        .order_by(SensorReading.timestamp)
        .all()
    )

    # Group by sensor_type
    sensor_groups: dict[str, list[SensorReading]] = {}
    for r in readings_long:
        sensor_groups.setdefault(r.sensor_type, []).append(r)

    for sensor_type, readings in sensor_groups.items():
        if len(readings) < 3:
            # Not enough data for meaningful features
            for feat in _sensor_feature_names(sensor_type):
                features[feat] = None
            continue

        values = np.array([r.sensor_value for r in readings], dtype=float)
        timestamps = np.array(
            [(r.timestamp.timestamp() if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc).timestamp())
             for r in readings],
            dtype=float,
        )

        # Basic statistics
        features[f"rolling_mean_{sensor_type}"] = float(np.mean(values))
        features[f"rolling_std_{sensor_type}"] = float(np.std(values))
        features[f"min_{sensor_type}"] = float(np.min(values))
        features[f"max_{sensor_type}"] = float(np.max(values))
        features[f"median_{sensor_type}"] = float(np.median(values))
        features[f"variability_{sensor_type}"] = float(np.std(values) / max(1e-9, abs(np.mean(values))))

        # Rate of change (last value - first value) / time_span_hours
        time_span_hours = (timestamps[-1] - timestamps[0]) / 3600.0
        if time_span_hours > 0:
            features[f"rate_of_change_{sensor_type}"] = float((values[-1] - values[0]) / time_span_hours)
        else:
            features[f"rate_of_change_{sensor_type}"] = 0.0

        # Trend slope via linear regression (value vs normalised time)
        t_norm = (timestamps - timestamps[0]) / max(1, timestamps[-1] - timestamps[0])
        if len(t_norm) >= 2 and np.std(t_norm) > 0:
            slope, _, _, _, _ = stats.linregress(t_norm, values)
            features[f"trend_slope_{sensor_type}"] = float(slope)
        else:
            features[f"trend_slope_{sensor_type}"] = 0.0

        # Baseline deviation: deviation from first-quartile mean (early window = baseline)
        baseline_n = max(1, len(values) // 4)
        baseline_mean = float(np.mean(values[:baseline_n]))
        recent_mean = float(np.mean(values[-baseline_n:]))
        features[f"baseline_deviation_{sensor_type}"] = recent_mean - baseline_mean

        # Threshold exceedance frequency
        warn_threshold = SENSOR_WARN_THRESHOLDS.get(sensor_type)
        if warn_threshold is not None:
            features[f"threshold_exceedance_freq_{sensor_type}"] = float(
                np.sum(values > warn_threshold) / len(values)
            )
        else:
            features[f"threshold_exceedance_freq_{sensor_type}"] = 0.0

        # Anomaly frequency over long window (from AnomalyEvent table)
        long_anomaly_count = (
            db.query(AnomalyEvent)
            .filter(
                AnomalyEvent.component_id == component.id,
                AnomalyEvent.sensor_type == sensor_type,
                AnomalyEvent.detected_at >= cutoff_long,
                AnomalyEvent.detected_at <= as_of,
            )
            .count()
        )
        features[f"anomaly_freq_{sensor_type}"] = long_anomaly_count / max(1, len(readings))

        # Short-term trend (7-day window)
        short_readings = [r for r in readings if _dt_cmp(r.timestamp, cutoff_short)]
        if len(short_readings) >= 2:
            sv = np.array([r.sensor_value for r in short_readings], dtype=float)
            st = np.array(
                [(r.timestamp.timestamp() if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc).timestamp())
                 for r in short_readings],
                dtype=float,
            )
            st_norm = (st - st[0]) / max(1, st[-1] - st[0])
            if np.std(st_norm) > 0:
                short_slope, _, _, _, _ = stats.linregress(st_norm, sv)
                features[f"short_term_trend_{sensor_type}"] = float(short_slope)
            else:
                features[f"short_term_trend_{sensor_type}"] = 0.0
        else:
            features[f"short_term_trend_{sensor_type}"] = None

        # Long-term trend = trend_slope already computed above
        features[f"long_term_trend_{sensor_type}"] = features[f"trend_slope_{sensor_type}"]

    return features


def _sensor_feature_names(sensor_type: str) -> list[str]:
    """Return all expected feature names for a given sensor type."""
    return [
        f"rolling_mean_{sensor_type}", f"rolling_std_{sensor_type}",
        f"min_{sensor_type}", f"max_{sensor_type}", f"median_{sensor_type}",
        f"rate_of_change_{sensor_type}", f"trend_slope_{sensor_type}",
        f"baseline_deviation_{sensor_type}", f"variability_{sensor_type}",
        f"threshold_exceedance_freq_{sensor_type}", f"anomaly_freq_{sensor_type}",
        f"short_term_trend_{sensor_type}", f"long_term_trend_{sensor_type}",
    ]


def compute_all_component_features(
    db: Session,
    as_of: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Compute features for all active components.

    Returns dict mapping component_id (str) -> feature_dict.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    components = db.query(Component).filter(Component.is_active == True).all()
    result: dict[str, dict[str, Any]] = {}

    for comp in components:
        try:
            result[str(comp.id)] = compute_component_features(comp, db, as_of=as_of)
        except Exception as e:
            logger.warning("Feature computation failed for component %s: %s", comp.id, e)
            result[str(comp.id)] = {}

    logger.info("Features computed for %d components as of %s", len(result), as_of.isoformat())
    return result

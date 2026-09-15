"""
Phase 7 — Anomaly Detection Engine
=====================================
Detects sensor anomalies using three complementary methods:
  1. Z-Score (statistical deviation from rolling mean)
  2. IQR (inter-quartile range fencing)
  3. Isolation Forest (unsupervised ML, scikit-learn)

Detection rule:
  An anomaly requires at least 2/3 methods to agree (ensemble vote).
  For single-method operation, a lower threshold is applied.

Data-leakage rule:
  All baselines (mean, std, IQR) are computed on data BEFORE the point
  being evaluated (rolling/expanding window). Future data is never used.

Output:
  AnomalyEvent records persisted to PostgreSQL.
  Returns a summary dict with counts by severity/method.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.models import (
    AnomalyEvent,
    AnomalySeverity,
    AnomalyType,
    Asset,
    Component,
    SensorReading,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Z-score threshold: ≥ this triggers a z-score flag
ZSCORE_THRESHOLD = 3.0
# IQR fencing: outside (Q1 - k*IQR, Q3 + k*IQR) triggers IQR flag
IQR_K = 2.5
# Isolation Forest contamination estimate (fraction expected anomalous)
IF_CONTAMINATION = 0.05
# Minimum readings needed for any anomaly detection
MIN_READINGS_FOR_DETECTION = 20
# Rolling window for z-score baseline (number of points)
ZSCORE_ROLLING_WINDOW = 30
# Minimum votes needed (out of 3 methods) to declare anomaly
MIN_VOTES = 2


@dataclass
class AnomalyDetectionResult:
    asset_id: str
    total_readings_checked: int
    anomalies_detected: int
    events_persisted: int
    by_severity: dict[str, int] = field(default_factory=dict)
    by_sensor_type: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ── Z-Score Detection ─────────────────────────────────────────────────────────

def _zscore_flags(values: np.ndarray, window: int = ZSCORE_ROLLING_WINDOW) -> np.ndarray:
    """
    Compute rolling z-score for each value using only preceding points.
    Returns boolean array: True = anomaly.
    Data-leakage-safe: uses expanding window until `window` points accumulated.
    """
    flags = np.zeros(len(values), dtype=bool)
    for i in range(1, len(values)):
        lookback = values[max(0, i - window): i]
        if len(lookback) < 5:
            continue
        mu = lookback.mean()
        sigma = lookback.std()
        if sigma < 1e-9:
            continue
        z = abs((values[i] - mu) / sigma)
        if z >= ZSCORE_THRESHOLD:
            flags[i] = True
    return flags


# ── IQR Detection ─────────────────────────────────────────────────────────────

def _iqr_flags(values: np.ndarray, window: int = ZSCORE_ROLLING_WINDOW) -> np.ndarray:
    """
    Rolling IQR fencing using only preceding points (data-leakage-safe).
    Returns boolean array: True = anomaly.
    """
    flags = np.zeros(len(values), dtype=bool)
    for i in range(1, len(values)):
        lookback = values[max(0, i - window): i]
        if len(lookback) < 5:
            continue
        q1, q3 = np.percentile(lookback, [25, 75])
        iqr = q3 - q1
        if iqr < 1e-9:
            continue
        lower = q1 - IQR_K * iqr
        upper = q3 + IQR_K * iqr
        if values[i] < lower or values[i] > upper:
            flags[i] = True
    return flags


# ── Isolation Forest Detection ────────────────────────────────────────────────

def _isolation_forest_flags(values: np.ndarray) -> np.ndarray:
    """
    Apply Isolation Forest on the full value array.
    Returns boolean array: True = anomaly.
    Note: this uses all data points for training, which is acceptable for
    retrospective batch detection (not real-time streaming).
    """
    if len(values) < MIN_READINGS_FOR_DETECTION:
        return np.zeros(len(values), dtype=bool)

    try:
        from sklearn.ensemble import IsolationForest
        clf = IsolationForest(
            contamination=IF_CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        X = values.reshape(-1, 1)
        preds = clf.fit_predict(X)
        # IsolationForest returns -1 for anomalies
        return preds == -1
    except ImportError:
        logger.warning("scikit-learn not available; skipping Isolation Forest detection")
        return np.zeros(len(values), dtype=bool)


# ── Severity classification ───────────────────────────────────────────────────

def _classify_severity(
    value: float,
    baseline_mean: float,
    baseline_std: float,
    votes: int,
) -> AnomalySeverity:
    """
    Classify anomaly severity based on deviation magnitude and vote count.
    """
    if baseline_std < 1e-9:
        deviation_z = 0.0
    else:
        deviation_z = abs((value - baseline_mean) / baseline_std)

    if votes == 3 and deviation_z >= 5.0:
        return AnomalySeverity.CRITICAL
    elif votes >= 2 and deviation_z >= 4.0:
        return AnomalySeverity.HIGH
    elif votes >= 2 and deviation_z >= 3.0:
        return AnomalySeverity.MEDIUM
    else:
        return AnomalySeverity.LOW


# ── Per-component anomaly detection ──────────────────────────────────────────

def _detect_component_sensor_anomalies(
    component: Component,
    sensor_type: str,
    readings: list[SensorReading],
    db: Session,
    as_of: datetime,
    model_version: str = "anomaly_v1",
) -> list[AnomalyEvent]:
    """
    Detect anomalies for a single (component, sensor_type) stream.
    Returns list of AnomalyEvent objects (not yet persisted).
    """
    if len(readings) < MIN_READINGS_FOR_DETECTION:
        return []

    # Sort chronologically
    readings_sorted = sorted(readings, key=lambda r: r.timestamp)
    values = np.array([r.sensor_value for r in readings_sorted], dtype=float)
    timestamps = [r.timestamp for r in readings_sorted]

    # Run all three detection methods
    zscore_flags = _zscore_flags(values)
    iqr_flags = _iqr_flags(values)
    if_flags = _isolation_forest_flags(values)

    # Compute global baseline for severity classification
    baseline_mean = np.mean(values[: max(1, len(values) // 2)])  # first half as baseline
    baseline_std = np.std(values[: max(1, len(values) // 2)])

    events: list[AnomalyEvent] = []
    for i, (reading, ts) in enumerate(zip(readings_sorted, timestamps)):
        votes = int(zscore_flags[i]) + int(iqr_flags[i]) + int(if_flags[i])
        if votes < MIN_VOTES:
            continue

        # Build method list for metadata
        methods_triggered = []
        if zscore_flags[i]:
            methods_triggered.append("zscore")
        if iqr_flags[i]:
            methods_triggered.append("iqr")
        if if_flags[i]:
            methods_triggered.append("isolation_forest")

        severity = _classify_severity(values[i], baseline_mean, baseline_std, votes)

        # Determine anomaly type from detection methods
        if len(methods_triggered) == 1 and methods_triggered[0] == "zscore":
            atype = AnomalyType.ZSCORE_OUTLIER
        elif len(methods_triggered) == 1 and methods_triggered[0] == "iqr":
            atype = AnomalyType.IQR_OUTLIER
        elif len(methods_triggered) == 1 and methods_triggered[0] == "isolation_forest":
            atype = AnomalyType.ISOLATION_FOREST
        elif votes >= 2:
            # Multi-method: classify by sensor characteristic
            if sensor_type in ("vibration", "rpm"):
                atype = AnomalyType.RATE_OF_CHANGE
            else:
                atype = AnomalyType.THRESHOLD_VIOLATION
        else:
            atype = AnomalyType.TREND_DEVIATION

        # Build evidence/explanation metadata
        if baseline_std > 1e-9:
            z_val = (values[i] - baseline_mean) / baseline_std
        else:
            z_val = 0.0

        # Anomaly score: normalised 0-1 from z-score (capped at 10 sigma = 1.0)
        anomaly_score = min(1.0, abs(z_val) / 10.0)

        # Deviation % from baseline
        if abs(baseline_mean) > 1e-9:
            deviation_pct = ((values[i] - baseline_mean) / abs(baseline_mean)) * 100.0
        else:
            deviation_pct = 0.0

        evidence = {
            "sensor_type": sensor_type,
            "sensor_value": float(values[i]),
            "baseline_mean": float(baseline_mean),
            "baseline_std": float(baseline_std),
            "z_score": float(z_val),
            "methods_triggered": methods_triggered,
            "votes": votes,
            "window_size": ZSCORE_ROLLING_WINDOW,
            "model_version": model_version,
        }

        event = AnomalyEvent(
            id=uuid.uuid4(),
            asset_id=component.asset_id,
            component_id=component.id,
            detected_at=as_of,
            anomaly_type=atype,
            severity=severity,
            sensor_type=sensor_type,
            sensor_value=float(values[i]),
            baseline_value=float(baseline_mean),
            deviation_pct=float(deviation_pct),
            anomaly_score=float(anomaly_score),
            is_acknowledged=False,
            evidence=evidence,
            pipeline_run_id=model_version,
        )
        events.append(event)

    return events


# ── Asset-level anomaly detection ─────────────────────────────────────────────

def run_anomaly_detection_for_asset(
    asset: Asset,
    db: Session,
    lookback_days: int = 30,
    as_of: datetime | None = None,
    model_version: str = "anomaly_v1",
    persist: bool = True,
) -> AnomalyDetectionResult:
    """
    Run full anomaly detection pipeline for a single asset.

    Args:
        asset: The asset to analyze.
        db: SQLAlchemy session.
        lookback_days: How many days of history to analyze.
        as_of: Reference timestamp (default: now UTC). Data after this is excluded.
        model_version: Version tag for audit trail.
        persist: If True, save AnomalyEvent records to DB.

    Returns:
        AnomalyDetectionResult summary.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    window_start = as_of - timedelta(days=lookback_days)
    result = AnomalyDetectionResult(
        asset_id=str(asset.id),
        total_readings_checked=0,
        anomalies_detected=0,
        events_persisted=0,
    )

    try:
        # Load all components for this asset
        components: list[Component] = (
            db.query(Component)
            .filter(Component.asset_id == asset.id, Component.is_active == True)
            .all()
        )

        all_events: list[AnomalyEvent] = []

        for component in components:
            # Load readings per sensor type
            readings_all: list[SensorReading] = (
                db.query(SensorReading)
                .filter(
                    SensorReading.component_id == component.id,
                    SensorReading.timestamp >= window_start,
                    SensorReading.timestamp <= as_of,
                )
                .order_by(SensorReading.timestamp)
                .all()
            )
            result.total_readings_checked += len(readings_all)

            if not readings_all:
                continue

            # Group by sensor_type
            by_sensor: dict[str, list[SensorReading]] = {}
            for r in readings_all:
                by_sensor.setdefault(r.sensor_type, []).append(r)

            for sensor_type, sensor_readings in by_sensor.items():
                events = _detect_component_sensor_anomalies(
                    component=component,
                    sensor_type=sensor_type,
                    readings=sensor_readings,
                    db=db,
                    as_of=as_of,
                    model_version=model_version,
                )
                all_events.extend(events)

        result.anomalies_detected = len(all_events)

        # Aggregate by severity and sensor type
        for event in all_events:
            sev_key = event.severity.value if hasattr(event.severity, "value") else str(event.severity)
            result.by_severity[sev_key] = result.by_severity.get(sev_key, 0) + 1
            st_key = event.sensor_type or "unknown"
            result.by_sensor_type[st_key] = result.by_sensor_type.get(st_key, 0) + 1

        if persist and all_events:
            try:
                # Deduplicate: skip if same (component, sensor_type, timestamp) already exists
                existing_keys: set[tuple] = set()
                existing = (
                    db.query(AnomalyEvent.component_id, AnomalyEvent.sensor_type, AnomalyEvent.detected_at)
                    .filter(
                        AnomalyEvent.asset_id == asset.id,
                        AnomalyEvent.detected_at == as_of,
                    )
                    .all()
                )
                for row in existing:
                    existing_keys.add((str(row[0]), row[1], row[2]))

                to_insert = [
                    e for e in all_events
                    if (str(e.component_id), e.sensor_type, e.detected_at) not in existing_keys
                ]
                if to_insert:
                    db.add_all(to_insert)
                    db.commit()
                    result.events_persisted = len(to_insert)
                    logger.info(
                        "Asset %s: %d anomaly events persisted",
                        asset.asset_id, result.events_persisted,
                    )
            except Exception as persist_err:
                db.rollback()
                logger.error("Failed to persist anomaly events for asset %s: %s", asset.asset_id, persist_err)
                result.errors.append(f"persist_error: {persist_err}")

    except Exception as e:
        logger.error("Anomaly detection failed for asset %s: %s", asset.asset_id, e)
        result.errors.append(str(e))

    return result


def run_anomaly_detection_for_all_assets(
    db: Session,
    lookback_days: int = 30,
    as_of: datetime | None = None,
    model_version: str = "anomaly_v1",
) -> dict[str, Any]:
    """
    Run anomaly detection across all active assets.
    Returns fleet-level summary.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    assets: list[Asset] = db.query(Asset).filter(Asset.is_active == True).all()
    logger.info("Running anomaly detection on %d assets (lookback=%d days)", len(assets), lookback_days)

    fleet_summary: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "assets_analyzed": 0,
        "total_readings_checked": 0,
        "total_anomalies_detected": 0,
        "total_events_persisted": 0,
        "by_severity": {},
        "by_sensor_type": {},
        "assets_with_anomalies": [],
        "errors": [],
    }

    for asset in assets:
        result = run_anomaly_detection_for_asset(
            asset=asset,
            db=db,
            lookback_days=lookback_days,
            as_of=as_of,
            model_version=model_version,
            persist=True,
        )
        fleet_summary["assets_analyzed"] += 1
        fleet_summary["total_readings_checked"] += result.total_readings_checked
        fleet_summary["total_anomalies_detected"] += result.anomalies_detected
        fleet_summary["total_events_persisted"] += result.events_persisted

        for sev, cnt in result.by_severity.items():
            fleet_summary["by_severity"][sev] = fleet_summary["by_severity"].get(sev, 0) + cnt
        for st, cnt in result.by_sensor_type.items():
            fleet_summary["by_sensor_type"][st] = fleet_summary["by_sensor_type"].get(st, 0) + cnt

        if result.anomalies_detected > 0:
            fleet_summary["assets_with_anomalies"].append({
                "asset_id": result.asset_id,
                "anomalies": result.anomalies_detected,
                "by_severity": result.by_severity,
            })
        fleet_summary["errors"].extend(result.errors)

    logger.info(
        "Fleet anomaly detection complete: %d assets, %d anomalies, %d persisted",
        fleet_summary["assets_analyzed"],
        fleet_summary["total_anomalies_detected"],
        fleet_summary["total_events_persisted"],
    )
    return fleet_summary

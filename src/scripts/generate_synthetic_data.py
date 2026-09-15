"""
Synthetic HUMS + Maintenance Dataset Generator
===============================================

Generates a reproducible realistic dataset with:
- 55 assets across multiple types
- 8-12 components per asset
- Multiple sensor streams per component
- Realistic health trajectories: healthy / degrading / high-risk
- Maintenance events that affect subsequent sensor values
- Intentional data quality problems (missing values, outliers, duplicates)

The generator produces PostgreSQL-ready data through SQLAlchemy.
No real military data. No hardcoded readiness outcomes.
Health states emerge from the underlying sensor/maintenance data.

Usage:
    python scripts/generate_synthetic_data.py [--seed 42] [--assets 55]
"""
import argparse
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import (
    Asset,
    AssetType,
    AuditLog,
    Component,
    MaintenanceRecord,
    MaintenanceType,
    SensorReading,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Constants ─────────────────────────────────────────────────────────────────

ASSET_TYPES = [
    AssetType.ROTARY_WING,
    AssetType.FIXED_WING,
    AssetType.GROUND_VEHICLE,
    AssetType.MARITIME,
    AssetType.SUPPORT_EQUIPMENT,
]

ASSET_TYPE_WEIGHTS = [0.35, 0.25, 0.25, 0.10, 0.05]

COMPONENT_TEMPLATES = {
    AssetType.ROTARY_WING: [
        {"id": "ENG", "name": "Main Engine", "type": "engine", "criticality": "HIGH",
         "design_life_hours": 2500, "sensors": ["temperature", "vibration", "rpm", "pressure"]},
        {"id": "GBOX", "name": "Main Gearbox", "type": "gearbox", "criticality": "HIGH",
         "design_life_hours": 3000, "sensors": ["temperature", "vibration", "pressure"]},
        {"id": "ROTOR", "name": "Main Rotor System", "type": "rotor", "criticality": "HIGH",
         "design_life_hours": 3500, "sensors": ["vibration", "rpm"]},
        {"id": "TAIL", "name": "Tail Rotor", "type": "rotor", "criticality": "HIGH",
         "design_life_hours": 3500, "sensors": ["vibration", "rpm"]},
        {"id": "HYD", "name": "Hydraulic System", "type": "hydraulic", "criticality": "MEDIUM",
         "design_life_hours": 5000, "sensors": ["pressure", "fluid_level", "temperature"]},
        {"id": "ELEC", "name": "Electrical System", "type": "electrical", "criticality": "MEDIUM",
         "design_life_hours": 8000, "sensors": ["voltage", "current"]},
        {"id": "FUEL", "name": "Fuel System", "type": "fuel", "criticality": "HIGH",
         "design_life_hours": 4000, "sensors": ["fluid_level", "pressure"]},
        {"id": "AVION", "name": "Avionics", "type": "avionics", "criticality": "MEDIUM",
         "design_life_hours": 10000, "sensors": ["voltage", "temperature"]},
        {"id": "AFRAME", "name": "Airframe", "type": "structure", "criticality": "HIGH",
         "design_life_hours": 20000, "sensors": ["vibration"]},
        {"id": "LNDG", "name": "Landing Gear", "type": "landing_gear", "criticality": "HIGH",
         "design_life_hours": 5000, "sensors": ["pressure", "cycle_count"]},
    ],
    AssetType.FIXED_WING: [
        {"id": "LENG", "name": "Left Engine", "type": "engine", "criticality": "HIGH",
         "design_life_hours": 4000, "sensors": ["temperature", "vibration", "rpm", "pressure"]},
        {"id": "RENG", "name": "Right Engine", "type": "engine", "criticality": "HIGH",
         "design_life_hours": 4000, "sensors": ["temperature", "vibration", "rpm", "pressure"]},
        {"id": "HYD", "name": "Hydraulic System", "type": "hydraulic", "criticality": "MEDIUM",
         "design_life_hours": 6000, "sensors": ["pressure", "fluid_level"]},
        {"id": "LNDG", "name": "Landing Gear", "type": "landing_gear", "criticality": "HIGH",
         "design_life_hours": 3000, "sensors": ["pressure", "cycle_count"]},
        {"id": "FUEL", "name": "Fuel System", "type": "fuel", "criticality": "HIGH",
         "design_life_hours": 5000, "sensors": ["fluid_level", "pressure"]},
        {"id": "ELEC", "name": "Electrical System", "type": "electrical", "criticality": "MEDIUM",
         "design_life_hours": 9000, "sensors": ["voltage", "current"]},
        {"id": "FLAP", "name": "Control Surfaces", "type": "flight_control", "criticality": "HIGH",
         "design_life_hours": 8000, "sensors": ["vibration", "cycle_count"]},
        {"id": "AVION", "name": "Avionics", "type": "avionics", "criticality": "MEDIUM",
         "design_life_hours": 12000, "sensors": ["voltage", "temperature"]},
        {"id": "AFRAME", "name": "Airframe", "type": "structure", "criticality": "HIGH",
         "design_life_hours": 25000, "sensors": ["vibration"]},
    ],
    AssetType.GROUND_VEHICLE: [
        {"id": "ENG", "name": "Drive Engine", "type": "engine", "criticality": "HIGH",
         "design_life_hours": 5000, "sensors": ["temperature", "vibration", "rpm", "pressure"]},
        {"id": "TRANS", "name": "Transmission", "type": "transmission", "criticality": "HIGH",
         "design_life_hours": 8000, "sensors": ["temperature", "vibration", "pressure"]},
        {"id": "BRAKE", "name": "Brake System", "type": "brakes", "criticality": "HIGH",
         "design_life_hours": 2000, "sensors": ["pressure", "temperature"]},
        {"id": "SUSP", "name": "Suspension", "type": "suspension", "criticality": "MEDIUM",
         "design_life_hours": 6000, "sensors": ["vibration", "cycle_count"]},
        {"id": "ELEC", "name": "Electrical System", "type": "electrical", "criticality": "MEDIUM",
         "design_life_hours": 10000, "sensors": ["voltage", "current"]},
        {"id": "FUEL", "name": "Fuel System", "type": "fuel", "criticality": "HIGH",
         "design_life_hours": 6000, "sensors": ["fluid_level", "pressure"]},
        {"id": "COOL", "name": "Cooling System", "type": "cooling", "criticality": "MEDIUM",
         "design_life_hours": 4000, "sensors": ["temperature", "fluid_level"]},
    ],
    AssetType.MARITIME: [
        {"id": "MENG", "name": "Main Engine", "type": "engine", "criticality": "HIGH",
         "design_life_hours": 8000, "sensors": ["temperature", "vibration", "rpm", "pressure"]},
        {"id": "PROP", "name": "Propulsion System", "type": "propulsion", "criticality": "HIGH",
         "design_life_hours": 6000, "sensors": ["vibration", "rpm", "pressure"]},
        {"id": "HELM", "name": "Steering System", "type": "steering", "criticality": "HIGH",
         "design_life_hours": 10000, "sensors": ["pressure", "vibration"]},
        {"id": "ELEC", "name": "Electrical System", "type": "electrical", "criticality": "MEDIUM",
         "design_life_hours": 15000, "sensors": ["voltage", "current"]},
        {"id": "PUMP", "name": "Bilge Pump", "type": "pump", "criticality": "MEDIUM",
         "design_life_hours": 5000, "sensors": ["pressure", "current", "vibration"]},
        {"id": "FUEL", "name": "Fuel System", "type": "fuel", "criticality": "HIGH",
         "design_life_hours": 8000, "sensors": ["fluid_level", "pressure"]},
    ],
    AssetType.SUPPORT_EQUIPMENT: [
        {"id": "ENG", "name": "Generator Engine", "type": "engine", "criticality": "MEDIUM",
         "design_life_hours": 3000, "sensors": ["temperature", "vibration", "rpm"]},
        {"id": "ELEC", "name": "Power Distribution", "type": "electrical", "criticality": "HIGH",
         "design_life_hours": 10000, "sensors": ["voltage", "current"]},
        {"id": "COOL", "name": "Cooling System", "type": "cooling", "criticality": "LOW",
         "design_life_hours": 4000, "sensors": ["temperature", "fluid_level"]},
        {"id": "HYD", "name": "Hydraulic System", "type": "hydraulic", "criticality": "MEDIUM",
         "design_life_hours": 5000, "sensors": ["pressure", "fluid_level"]},
    ],
}

# Sensor baseline parameters: (mean, std, unit, normal_range)
SENSOR_PARAMS: dict[str, dict[str, Any]] = {
    "temperature": {"mean": 85.0, "std": 5.0, "unit": "°C", "min_valid": 20.0, "max_valid": 200.0, "warn_high": 110.0, "crit_high": 135.0},
    "vibration":   {"mean": 2.5,  "std": 0.3, "unit": "mm/s", "min_valid": 0.0, "max_valid": 50.0, "warn_high": 7.0, "crit_high": 12.0},
    "pressure":    {"mean": 45.0, "std": 3.0, "unit": "bar", "min_valid": 5.0, "max_valid": 150.0, "warn_high": 65.0, "crit_high": 80.0},
    "rpm":         {"mean": 2400.0, "std": 50.0, "unit": "rpm", "min_valid": 0.0, "max_valid": 8000.0, "warn_high": 3200.0, "crit_high": 3800.0},
    "voltage":     {"mean": 28.0, "std": 0.5, "unit": "V", "min_valid": 18.0, "max_valid": 35.0, "warn_high": 31.0, "crit_high": 33.0},
    "current":     {"mean": 15.0, "std": 1.5, "unit": "A", "min_valid": 0.0, "max_valid": 100.0, "warn_high": 30.0, "crit_high": 45.0},
    "fluid_level": {"mean": 78.0, "std": 5.0, "unit": "%", "min_valid": 0.0, "max_valid": 100.0, "warn_high": 95.0, "crit_high": 99.0},
    "operating_hours": {"mean": 0.5, "std": 0.1, "unit": "hr", "min_valid": 0.0, "max_valid": 24.0, "warn_high": 18.0, "crit_high": 22.0},
    "cycle_count": {"mean": 3.0, "std": 1.0, "unit": "cycles", "min_valid": 0.0, "max_valid": 500.0, "warn_high": 20.0, "crit_high": 30.0},
}

# Asset health categories with approximate distribution
HEALTH_CATEGORIES = ["healthy", "degrading_early", "degrading_advanced", "high_risk", "recovering"]
HEALTH_WEIGHTS = [0.50, 0.20, 0.15, 0.10, 0.05]

FLEET_NAMES = ["Alpha Squadron", "Bravo Squadron", "Charlie Battalion", "Delta Group", "Echo Fleet"]
TECHNICIAN_NAMES = [
    "Sgt. Morrison", "Cpl. Reeves", "Tech. Williams", "WO Patel", "Sgt. Chen",
    "Cpl. Rodriguez", "Tech. O'Brien", "WO Kumar", "Sgt. Jackson", "Cpl. Novak",
]


class SyntheticDataGenerator:
    """
    Generates reproducible realistic HUMS + maintenance synthetic data.

    Health states emerge from the underlying sensor patterns — they are NOT
    directly assigned. Analytics will discover them from the generated data.
    """

    def __init__(self, seed: int = 42, num_assets: int = 55):
        self.seed = seed
        self.num_assets = num_assets
        self.rng = np.random.default_rng(seed)
        random.seed(seed)
        self._now = datetime.now(timezone.utc)
        self._history_start = self._now - timedelta(days=365)

    def _rand(self) -> float:
        return self.rng.random()

    def _normal(self, mean: float, std: float) -> float:
        return float(self.rng.normal(mean, std))

    def _choice(self, seq: list, weights: list | None = None):
        if weights:
            total = sum(weights)
            normalized = [w / total for w in weights]
            idx = self.rng.choice(len(seq), p=normalized)
            return seq[idx]
        return seq[int(self.rng.integers(0, len(seq)))]

    def generate_assets(self) -> list[Asset]:
        """Generate Asset records."""
        assets = []
        for i in range(self.num_assets):
            asset_type = self._choice(ASSET_TYPES, ASSET_TYPE_WEIGHTS)
            asset_id = f"{asset_type.value[:2]}-{1001 + i:04d}"
            fleet = FLEET_NAMES[i % len(FLEET_NAMES)]

            # Vary operating hours realistically
            age_years = self._normal(3.5, 1.8)
            age_years = max(0.5, min(12.0, age_years))
            total_hours = age_years * self._normal(400, 80)
            total_hours = max(50.0, total_hours)

            manufacture_date = self._now - timedelta(days=age_years * 365)

            asset = Asset(
                id=uuid.uuid4(),
                asset_id=asset_id,
                name=f"{asset_type.value.replace('_', ' ').title()} {1001 + i}",
                asset_type=asset_type,
                fleet=fleet,
                location=f"Base {chr(65 + (i % 8))}",
                serial_number=f"SN-{asset_id}-{uuid.uuid4().hex[:6].upper()}",
                manufacture_date=manufacture_date,
                total_operating_hours=round(total_hours, 1),
                total_cycles=int(total_hours * self._normal(2.5, 0.5)),
                is_active=True,
            )
            assets.append(asset)
        return assets

    def generate_components(self, asset: Asset) -> list[Component]:
        """Generate Component records for an asset."""
        templates = COMPONENT_TEMPLATES.get(asset.asset_type, COMPONENT_TEMPLATES[AssetType.GROUND_VEHICLE])

        # Use all available components (templates are already 6–10 per type)
        # clamp to [max(4, len), max(4, len)] to avoid low>=high in randint
        lo = min(4, len(templates))
        hi = len(templates) + 1
        n_components = int(self.rng.integers(lo, hi))
        selected = templates[:n_components]

        components = []
        for tmpl in selected:
            # Component age may differ from asset age (replacements happen)
            comp_hours_fraction = self._normal(0.75, 0.2)
            comp_hours_fraction = max(0.05, min(1.2, comp_hours_fraction))
            comp_hours = asset.total_operating_hours * comp_hours_fraction

            install_offset_days = int((1.0 - comp_hours_fraction) * (self._now - asset.manufacture_date).days)
            install_date = asset.manufacture_date + timedelta(days=install_offset_days)

            comp = Component(
                id=uuid.uuid4(),
                asset_id=asset.id,
                component_id=f"{asset.asset_id}-{tmpl['id']}",
                name=tmpl["name"],
                component_type=tmpl["type"],
                criticality=tmpl["criticality"],
                install_date=install_date,
                design_life_hours=tmpl["design_life_hours"],
                current_operating_hours=round(comp_hours, 1),
                current_cycles=int(comp_hours * self._normal(2.5, 0.5)),
                is_active=True,
            )
            components.append(comp)
        return components

    def _get_health_category(self, asset: Asset) -> str:
        """
        Assign a health trajectory to an asset.
        Distribution: 50% healthy, 20% early degradation, 15% advanced, 10% high risk, 5% recovering.
        This is used to generate sensor patterns — NOT to hardcode readiness outcomes.
        """
        h = self._rand()
        cumulative = 0.0
        for cat, weight in zip(HEALTH_CATEGORIES, HEALTH_WEIGHTS):
            cumulative += weight
            if h < cumulative:
                return cat
        return "healthy"

    def generate_sensor_readings(
        self,
        asset: Asset,
        components: list[Component],
        health_category: str,
        readings_per_component_per_day: float = 4.0,
    ) -> list[SensorReading]:
        """
        Generate realistic sensor readings reflecting the component health trajectory.

        - healthy: stable readings with normal noise
        - degrading_early: gradual drift upward on temperature/vibration
        - degrading_advanced: faster drift, increased variability
        - high_risk: multiple threshold exceedances, correlated signals
        - recovering: readings improve after maintenance window
        """
        readings = []
        history_days = (self._now - self._history_start).days

        for comp in components:
            templates = COMPONENT_TEMPLATES.get(asset.asset_type, [])
            comp_template = next((t for t in templates if t["id"] == comp.component_id.split("-")[-1]), None)
            if comp_template is None:
                # Fallback: determine sensors from component type
                sensors = ["temperature", "vibration"]
            else:
                sensors = comp_template["sensors"]

            # Determine degradation onset
            if health_category == "healthy":
                degradation_start_day = history_days + 999  # never
                degradation_severity = 0.0
            elif health_category == "degrading_early":
                degradation_start_day = int(history_days * self._normal(0.6, 0.1))
                degradation_severity = self._normal(0.25, 0.08)
            elif health_category == "degrading_advanced":
                degradation_start_day = int(history_days * self._normal(0.35, 0.1))
                degradation_severity = self._normal(0.55, 0.12)
            elif health_category == "high_risk":
                degradation_start_day = int(history_days * self._normal(0.25, 0.1))
                degradation_severity = self._normal(0.80, 0.10)
            else:  # recovering
                degradation_start_day = int(history_days * 0.2)
                degradation_severity = self._normal(0.6, 0.1)

            # Maintenance recovery window for 'recovering' assets
            recovery_start_day = int(history_days * 0.75) if health_category == "recovering" else 9999

            for sensor_type in sensors:
                params = SENSOR_PARAMS.get(sensor_type, SENSOR_PARAMS["temperature"])
                baseline_mean = params["mean"] + self._normal(0, params["std"] * 0.3)

                # Readings at specified cadence with jitter
                sample_interval_hours = 24.0 / readings_per_component_per_day

                current_dt = self._history_start
                while current_dt < self._now:
                    # Use actual elapsed calendar days for degradation timing
                    elapsed_days = (current_dt - self._history_start).total_seconds() / 86400.0

                    # Calculate degradation factor based on actual day
                    if elapsed_days >= degradation_start_day:
                        days_since_onset = elapsed_days - degradation_start_day
                        total_degradation_days = max(1, history_days - degradation_start_day)
                        progress = min(1.0, days_since_onset / total_degradation_days)
                        degradation_factor = degradation_severity * progress
                    else:
                        degradation_factor = 0.0

                    # Recovery effect
                    if elapsed_days >= recovery_start_day:
                        days_since_recovery = elapsed_days - recovery_start_day
                        recovery_progress = min(1.0, days_since_recovery / 30.0)
                        degradation_factor *= (1.0 - recovery_progress * 0.8)

                    # Add correlated degradation for high-risk assets (multiple sensors worsen together)
                    if health_category == "high_risk" and sensor_type in ["vibration", "temperature"]:
                        degradation_factor *= 1.3

                    # Generate value
                    noise = self._normal(0, params["std"])
                    degraded_mean = baseline_mean + (params["warn_high"] - baseline_mean) * degradation_factor
                    value = degraded_mean + noise

                    # Occasional spikes (especially in degrading assets)
                    spike_probability = 0.002 + 0.015 * degradation_factor
                    if self._rand() < spike_probability:
                        value = value + self._normal(params["warn_high"] * 0.4, params["std"] * 2)

                    # Clip to physically plausible range
                    value = max(params["min_valid"] * 0.5, min(params["max_valid"] * 1.2, value))

                    # Intentional data quality issues (plan requirement)
                    quality_flag = "OK"
                    inject_quality_issue = self._rand()
                    if inject_quality_issue < 0.003:
                        # Sensor gap / missing — skip this reading entirely
                        current_dt += timedelta(hours=sample_interval_hours * self._normal(1.0, 0.15))
                        continue
                    elif inject_quality_issue < 0.006:
                        # Invalid range value
                        value = params["max_valid"] * self._normal(1.5, 0.2)
                        quality_flag = "RANGE_VIOLATION"
                    elif inject_quality_issue < 0.009:
                        # Outlier spike
                        value = baseline_mean + params["std"] * self._normal(4.5, 0.5)
                        quality_flag = "OUTLIER"

                    # Occasional duplicates (plan requirement)
                    reading = SensorReading(
                        id=uuid.uuid4(),
                        asset_id=asset.id,
                        component_id=comp.id,
                        timestamp=current_dt,
                        sensor_type=sensor_type,
                        sensor_value=round(value, 4),
                        unit=params["unit"],
                        quality_flag=quality_flag,
                        ingestion_batch_id="synthetic_v1",
                    )
                    readings.append(reading)

                    # Duplicate injection (plan requirement)
                    if self._rand() < 0.002:
                        dup = SensorReading(
                            id=uuid.uuid4(),
                            asset_id=asset.id,
                            component_id=comp.id,
                            timestamp=current_dt,  # same timestamp = duplicate
                            sensor_type=sensor_type,
                            sensor_value=round(value, 4),
                            unit=params["unit"],
                            quality_flag="DUPLICATE",
                            ingestion_batch_id="synthetic_v1",
                        )
                        readings.append(dup)

                    # Advance time with slight jitter
                    current_dt += timedelta(hours=sample_interval_hours * self._normal(1.0, 0.1))

        return readings

    def generate_maintenance_records(
        self, asset: Asset, components: list[Component], health_category: str
    ) -> list[MaintenanceRecord]:
        """Generate maintenance history appropriate for the asset's health trajectory."""
        records = []
        history_days = (self._now - self._history_start).days

        # Base scheduled maintenance interval in days
        base_interval = 90 if asset.asset_type in [AssetType.ROTARY_WING, AssetType.FIXED_WING] else 120

        # Number of scheduled maintenance events in history
        n_scheduled = max(1, int(history_days / base_interval))

        for i in range(n_scheduled):
            maint_day = int(history_days * (i + 1) / (n_scheduled + 1))
            maint_date = self._history_start + timedelta(days=maint_day)

            comp = components[int(self.rng.integers(0, len(components)))]

            record = MaintenanceRecord(
                id=uuid.uuid4(),
                maintenance_event_id=f"M-{asset.asset_id}-SCH-{i + 1:04d}",
                asset_id=asset.id,
                component_id=comp.id,
                maintenance_date=maint_date,
                maintenance_type=MaintenanceType.SCHEDULED,
                description=f"Scheduled maintenance interval {i + 1}. Inspection and servicing.",
                technician=random.choice(TECHNICIAN_NAMES),
                operating_hours_at_maintenance=round(
                    asset.total_operating_hours * maint_day / history_days, 1
                ),
                outcome="COMPLETED",
            )
            records.append(record)

        # Unscheduled maintenance for degrading/high-risk assets
        if health_category in ["degrading_advanced", "high_risk", "recovering"]:
            n_unscheduled = int(self.rng.integers(1, 4))
            for i in range(n_unscheduled):
                maint_day = int(history_days * self._normal(0.65, 0.15))
                maint_day = max(30, min(history_days - 7, maint_day))
                maint_date = self._history_start + timedelta(days=maint_day)

                # Pick a critical component
                critical_comps = [c for c in components if c.criticality == "HIGH"] or components
                comp = critical_comps[int(self.rng.integers(0, len(critical_comps)))]

                fault_codes = [f"FAULT-{int(self.rng.integers(100, 999))}"]
                record = MaintenanceRecord(
                    id=uuid.uuid4(),
                    maintenance_event_id=f"M-{asset.asset_id}-UNS-{i + 1:04d}",
                    asset_id=asset.id,
                    component_id=comp.id,
                    maintenance_date=maint_date,
                    maintenance_type=MaintenanceType.UNSCHEDULED
                    if self._rand() > 0.4 else MaintenanceType.FAULT,
                    description=f"Unscheduled maintenance following anomaly detection. Fault: {fault_codes[0]}",
                    technician=random.choice(TECHNICIAN_NAMES),
                    operating_hours_at_maintenance=round(
                        asset.total_operating_hours * maint_day / history_days, 1
                    ),
                    fault_codes=fault_codes,
                    outcome="COMPLETED",
                )
                records.append(record)

        # Component replacements (realistic for aged assets)
        if asset.total_operating_hours > 1500 and self._rand() < 0.4:
            comp = components[int(self.rng.integers(0, len(components)))]
            repl_day = int(history_days * self._normal(0.5, 0.15))
            repl_date = self._history_start + timedelta(days=repl_day)

            record = MaintenanceRecord(
                id=uuid.uuid4(),
                maintenance_event_id=f"M-{asset.asset_id}-REPL-0001",
                asset_id=asset.id,
                component_id=comp.id,
                maintenance_date=repl_date,
                maintenance_type=MaintenanceType.REPLACEMENT,
                description=f"Component replacement: {comp.name}. Life-limit reached.",
                technician=random.choice(TECHNICIAN_NAMES),
                operating_hours_at_maintenance=round(comp.current_operating_hours * 0.85, 1),
                parts_replaced=[{"component": comp.name, "reason": "life_limit"}],
                outcome="COMPLETED",
            )
            records.append(record)

        return records

    def generate_all(self, db) -> dict[str, int]:
        """
        Generate the complete synthetic dataset and persist to PostgreSQL.
        Returns counts of created entities.
        """
        logger.info("Generating synthetic dataset (seed=%d, assets=%d)...", self.seed, self.num_assets)

        counts: dict[str, int] = {
            "assets": 0,
            "components": 0,
            "sensor_readings": 0,
            "maintenance_records": 0,
        }

        assets = self.generate_assets()

        for i, asset in enumerate(assets):
            health_category = self._get_health_category(asset)
            logger.info(
                "  [%d/%d] %s — health category: %s",
                i + 1, len(assets), asset.asset_id, health_category,
            )

            # Components
            components = self.generate_components(asset)

            # Sensor readings (use fewer readings per day for large datasets)
            readings_per_day = 2.0 if self.num_assets > 40 else 4.0
            sensor_readings = self.generate_sensor_readings(
                asset, components, health_category, readings_per_component_per_day=readings_per_day
            )

            # Maintenance records
            maintenance_records = self.generate_maintenance_records(asset, components, health_category)

            # Persist in batches
            db.add(asset)
            db.flush()  # get asset.id

            for comp in components:
                db.add(comp)
            db.flush()

            for reading in sensor_readings:
                db.add(reading)

            for record in maintenance_records:
                db.add(record)

            # Commit per asset to avoid huge transactions
            db.commit()

            counts["assets"] += 1
            counts["components"] += len(components)
            counts["sensor_readings"] += len(sensor_readings)
            counts["maintenance_records"] += len(maintenance_records)

        # Write audit log entry
        audit = AuditLog(
            id=uuid.uuid4(),
            event_type="synthetic_data_generation",
            input_summary={
                "seed": self.seed,
                "num_assets": self.num_assets,
            },
            result=counts,
            model_version="synthetic_v1",
            pipeline_run_id="synthetic_generation",
            user_or_system="synthetic_generator",
        )
        db.add(audit)
        db.commit()

        logger.info("Generation complete: %s", counts)
        return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Generate synthetic HUMS dataset")
    parser.add_argument("--seed", type=int, default=settings.synthetic_data_seed, help="RNG seed")
    parser.add_argument("--assets", type=int, default=55, help="Number of assets to generate")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before generating (USE WITH CAUTION)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.clear:
            logger.warning("Clearing existing data...")
            from app.models.models import (
                AnomalyEvent,
                AuditLog,
                DataQualityReport,
                MaintenanceRecommendation,
                Prediction,
                ReadinessAssessment,
            )
            for model in [
                AuditLog, MaintenanceRecommendation, DataQualityReport,
                ReadinessAssessment, Prediction, AnomalyEvent,
                MaintenanceRecord, SensorReading, Component, Asset,
            ]:
                db.query(model).delete()
            db.commit()
            logger.info("Existing data cleared.")

        generator = SyntheticDataGenerator(seed=args.seed, num_assets=args.assets)
        counts = generator.generate_all(db)
        print(f"\n[OK] Synthetic data generation complete:")
        for entity, count in counts.items():
            print(f"  {entity}: {count:,}")
    except Exception as e:
        logger.error("Generation failed: %s", e)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

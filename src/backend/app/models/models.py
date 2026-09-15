"""
SQLAlchemy ORM models for the HUMS / Predictive Maintenance platform.

Entities:
  Asset, Component, SensorReading, MaintenanceRecord, AnomalyEvent,
  Prediction, ReadinessAssessment, MaintenanceRecommendation,
  DataQualityReport, AuditLog
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ── Enumerations ──────────────────────────────────────────────────────────────

class AssetType(str, enum.Enum):
    AIRCRAFT = "AIRCRAFT"
    GROUND_VEHICLE = "GROUND_VEHICLE"
    MARITIME = "MARITIME"
    ROTARY_WING = "ROTARY_WING"
    FIXED_WING = "FIXED_WING"
    SUPPORT_EQUIPMENT = "SUPPORT_EQUIPMENT"


class ReadinessStatus(str, enum.Enum):
    READY = "READY"
    READY_WITH_CAUTION = "READY_WITH_CAUTION"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"
    NOT_READY = "NOT_READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RiskCategory(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MaintenanceType(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    UNSCHEDULED = "UNSCHEDULED"
    INSPECTION = "INSPECTION"
    REPLACEMENT = "REPLACEMENT"
    REPAIR = "REPAIR"
    OVERHAUL = "OVERHAUL"
    FAULT = "FAULT"


class AnomalySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnomalyType(str, enum.Enum):
    THRESHOLD_VIOLATION = "THRESHOLD_VIOLATION"
    ZSCORE_OUTLIER = "ZSCORE_OUTLIER"
    IQR_OUTLIER = "IQR_OUTLIER"
    ISOLATION_FOREST = "ISOLATION_FOREST"
    TREND_DEVIATION = "TREND_DEVIATION"
    RATE_OF_CHANGE = "RATE_OF_CHANGE"


class MaintenancePriority(str, enum.Enum):
    IMMEDIATE = "IMMEDIATE"
    HIGH = "HIGH"
    PLANNED = "PLANNED"
    MONITOR = "MONITOR"


class ReviewStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class DataQualityLevel(str, enum.Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    INSUFFICIENT = "INSUFFICIENT"


class SensorType(str, enum.Enum):
    TEMPERATURE = "temperature"
    VIBRATION = "vibration"
    PRESSURE = "pressure"
    RPM = "rpm"
    VOLTAGE = "voltage"
    CURRENT = "current"
    FLUID_LEVEL = "fluid_level"
    OPERATING_HOURS = "operating_hours"
    CYCLE_COUNT = "cycle_count"


# ── Mixins ────────────────────────────────────────────────────────────────────

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


# ── Asset ─────────────────────────────────────────────────────────────────────

class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A physical asset (aircraft, vehicle, equipment).
    """
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type_enum"), nullable=False
    )
    fleet: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    manufacture_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_operating_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_cycles: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Relationships
    components: Mapped[list["Component"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    sensor_readings: Mapped[list["SensorReading"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    maintenance_records: Mapped[list["MaintenanceRecord"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    readiness_assessments: Mapped[list["ReadinessAssessment"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    data_quality_reports: Mapped[list["DataQualityReport"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Asset {self.asset_id} ({self.asset_type})>"


# ── Component ─────────────────────────────────────────────────────────────────

class Component(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A sub-component of an asset (engine, rotor, hydraulic system, etc.).
    """
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("asset_id", "component_id", name="uq_component_per_asset"),
        Index("ix_components_asset_id", "asset_id"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    component_type: Mapped[str] = mapped_column(String(100), nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model_number: Mapped[str | None] = mapped_column(String(100))
    install_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    design_life_hours: Mapped[float | None] = mapped_column(Float)
    design_life_cycles: Mapped[int | None] = mapped_column(Integer)
    current_operating_hours: Mapped[float] = mapped_column(Float, default=0.0)
    current_cycles: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="components")
    sensor_readings: Mapped[list["SensorReading"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    maintenance_records: Mapped[list["MaintenanceRecord"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    anomaly_events: Mapped[list["AnomalyEvent"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    maintenance_recommendations: Mapped[list["MaintenanceRecommendation"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Component {self.component_id} on asset {self.asset_id}>"


# ── SensorReading ─────────────────────────────────────────────────────────────

class SensorReading(UUIDPrimaryKeyMixin, Base):
    """
    Individual sensor measurement from a component/asset.
    """
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_asset_ts", "asset_id", "timestamp"),
        Index("ix_sensor_readings_component_ts", "component_id", "timestamp"),
        Index("ix_sensor_readings_sensor_type", "sensor_type"),
        Index("ix_sensor_readings_timestamp", "timestamp"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sensor_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30))
    quality_flag: Mapped[str | None] = mapped_column(String(20))  # OK, MISSING, OUTLIER, etc.
    ingestion_batch_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="sensor_readings")
    component: Mapped["Component | None"] = relationship(back_populates="sensor_readings")

    def __repr__(self) -> str:
        return (
            f"<SensorReading asset={self.asset_id} "
            f"sensor={self.sensor_type} ts={self.timestamp}>"
        )


# ── MaintenanceRecord ─────────────────────────────────────────────────────────

class MaintenanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Historical maintenance event on an asset/component.
    """
    __tablename__ = "maintenance_records"
    __table_args__ = (
        Index("ix_maintenance_records_asset_date", "asset_id", "maintenance_date"),
        Index("ix_maintenance_records_component_date", "component_id", "maintenance_date"),
    )

    maintenance_event_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    maintenance_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    maintenance_type: Mapped[MaintenanceType] = mapped_column(
        Enum(MaintenanceType, name="maintenance_type_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    technician: Mapped[str | None] = mapped_column(String(200))
    operating_hours_at_maintenance: Mapped[float | None] = mapped_column(Float)
    cycles_at_maintenance: Mapped[int | None] = mapped_column(Integer)
    fault_codes: Mapped[list | None] = mapped_column(JSONB)
    parts_replaced: Mapped[list | None] = mapped_column(JSONB)
    outcome: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="maintenance_records")
    component: Mapped["Component | None"] = relationship(
        back_populates="maintenance_records"
    )

    def __repr__(self) -> str:
        return (
            f"<MaintenanceRecord {self.maintenance_event_id} "
            f"type={self.maintenance_type} date={self.maintenance_date}>"
        )


# ── AnomalyEvent ──────────────────────────────────────────────────────────────

class AnomalyEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Detected anomaly on a component sensor reading.
    """
    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_events_component_ts", "component_id", "detected_at"),
        Index("ix_anomaly_events_severity", "severity"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    sensor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anomaly_type: Mapped[AnomalyType] = mapped_column(
        Enum(AnomalyType, name="anomaly_type_enum"), nullable=False
    )
    severity: Mapped[AnomalySeverity] = mapped_column(
        Enum(AnomalySeverity, name="anomaly_severity_enum"), nullable=False
    )
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    sensor_value: Mapped[float | None] = mapped_column(Float)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    deviation_pct: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    component: Mapped["Component | None"] = relationship(back_populates="anomaly_events")

    def __repr__(self) -> str:
        return (
            f"<AnomalyEvent component={self.component_id} "
            f"severity={self.severity} at={self.detected_at}>"
        )


# ── Prediction ────────────────────────────────────────────────────────────────

class Prediction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Risk/failure prediction for a component.
    """
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_component_ts", "component_id", "predicted_at"),
        Index("ix_predictions_risk_category", "risk_category"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0–1.0
    risk_category: Mapped[RiskCategory] = mapped_column(
        Enum(RiskCategory, name="risk_category_enum"), nullable=False
    )
    risk_factors: Mapped[list | None] = mapped_column(JSONB)
    feature_values: Mapped[dict | None] = mapped_column(JSONB)
    uncertainty: Mapped[float | None] = mapped_column(Float)
    data_sufficiency: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    model_version: Mapped[str | None] = mapped_column(String(50))
    layer_scores: Mapped[dict | None] = mapped_column(JSONB)  # L1/L2/L3 breakdown
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    component: Mapped["Component"] = relationship(back_populates="predictions")

    def __repr__(self) -> str:
        return (
            f"<Prediction component={self.component_id} "
            f"risk={self.risk_category} score={self.risk_score:.2f}>"
        )


# ── ReadinessAssessment ───────────────────────────────────────────────────────

class ReadinessAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Fleet readiness assessment for an asset.
    """
    __tablename__ = "readiness_assessments"
    __table_args__ = (
        Index("ix_readiness_assessments_asset_ts", "asset_id", "assessed_at"),
        Index("ix_readiness_assessments_status", "status"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReadinessStatus] = mapped_column(
        Enum(ReadinessStatus, name="readiness_status_enum"), nullable=False
    )
    overall_health_score: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    primary_evidence: Mapped[list | None] = mapped_column(JSONB)
    component_summary: Mapped[dict | None] = mapped_column(JSONB)
    data_quality_score: Mapped[float | None] = mapped_column(Float)
    prediction_horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    explanation: Mapped[str | None] = mapped_column(Text)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="readiness_assessments")

    def __repr__(self) -> str:
        return (
            f"<ReadinessAssessment asset={self.asset_id} "
            f"status={self.status} at={self.assessed_at}>"
        )


# ── MaintenanceRecommendation ─────────────────────────────────────────────────

class MaintenanceRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Prioritized maintenance recommendation generated by the analytics engine.
    """
    __tablename__ = "maintenance_recommendations"
    __table_args__ = (
        Index("ix_maint_rec_priority", "priority"),
        Index("ix_maint_rec_asset_id", "asset_id"),
        Index("ix_maint_rec_review_status", "review_status"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[MaintenancePriority] = mapped_column(
        Enum(MaintenancePriority, name="maintenance_priority_enum"), nullable=False
    )
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list | None] = mapped_column(JSONB)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    urgency_days: Mapped[int | None] = mapped_column(Integer)
    prediction_window_days: Mapped[int | None] = mapped_column(Integer)
    risk_score: Mapped[float | None] = mapped_column(Float)
    data_confidence: Mapped[float | None] = mapped_column(Float)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status_enum"), default=ReviewStatus.PENDING
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    component: Mapped["Component"] = relationship(
        back_populates="maintenance_recommendations"
    )

    def __repr__(self) -> str:
        return (
            f"<MaintenanceRecommendation component={self.component_id} "
            f"priority={self.priority} review={self.review_status}>"
        )


# ── DataQualityReport ─────────────────────────────────────────────────────────

class DataQualityReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Data quality metrics for an asset's sensor readings.
    """
    __tablename__ = "data_quality_reports"
    __table_args__ = (
        Index("ix_dqr_asset_ts", "asset_id", "report_date"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False)
    validity_score: Mapped[float] = mapped_column(Float, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, nullable=False)
    timeliness_score: Mapped[float] = mapped_column(Float, nullable=False)
    duplicate_rate: Mapped[float] = mapped_column(Float, nullable=False)
    missing_value_rate: Mapped[float] = mapped_column(Float, nullable=False)
    outlier_rate: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_level: Mapped[DataQualityLevel] = mapped_column(
        Enum(DataQualityLevel, name="data_quality_level_enum"), nullable=False
    )
    total_records: Mapped[int] = mapped_column(Integer, nullable=False)
    issues_detail: Mapped[dict | None] = mapped_column(JSONB)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="data_quality_reports")

    def __repr__(self) -> str:
        return (
            f"<DataQualityReport asset={self.asset_id} "
            f"score={self.overall_score:.2f} level={self.quality_level}>"
        )


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(UUIDPrimaryKeyMixin, Base):
    """
    Immutable audit trail for all analytics decisions and actions.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_asset_ts", "asset_id", "timestamp"),
        Index("ix_audit_logs_event_type", "event_type"),
        Index("ix_audit_logs_pipeline_run", "pipeline_run_id"),
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    input_summary: Mapped[dict | None] = mapped_column(JSONB)
    calculation_details: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    model_version: Mapped[str | None] = mapped_column(String(50))
    pipeline_run_id: Mapped[str | None] = mapped_column(String(100))
    user_or_system: Mapped[str] = mapped_column(String(200), default="system")

    def __repr__(self) -> str:
        return f"<AuditLog event={self.event_type} at={self.timestamp}>"

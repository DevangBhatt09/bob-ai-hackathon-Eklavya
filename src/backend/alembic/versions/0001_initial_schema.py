"""Initial schema: all HUMS platform tables

Revision ID: 0001_initial_schema
Revises:
Create Date: 2025-01-01 00:00:00.000000

This migration uses raw SQL throughout to avoid SQLAlchemy ORM Enum
auto-create/drop events causing DuplicateObject errors.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        DO $$ BEGIN

        -- Enum types (idempotent)
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'asset_type_enum') THEN
            CREATE TYPE asset_type_enum AS ENUM ('AIRCRAFT','GROUND_VEHICLE','MARITIME','ROTARY_WING','FIXED_WING','SUPPORT_EQUIPMENT');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'readiness_status_enum') THEN
            CREATE TYPE readiness_status_enum AS ENUM ('READY','READY_WITH_CAUTION','MAINTENANCE_REQUIRED','NOT_READY','INSUFFICIENT_DATA');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'risk_category_enum') THEN
            CREATE TYPE risk_category_enum AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'maintenance_type_enum') THEN
            CREATE TYPE maintenance_type_enum AS ENUM ('SCHEDULED','UNSCHEDULED','INSPECTION','REPLACEMENT','REPAIR','OVERHAUL','FAULT');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anomaly_type_enum') THEN
            CREATE TYPE anomaly_type_enum AS ENUM ('THRESHOLD_VIOLATION','ZSCORE_OUTLIER','IQR_OUTLIER','ISOLATION_FOREST','TREND_DEVIATION','RATE_OF_CHANGE');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anomaly_severity_enum') THEN
            CREATE TYPE anomaly_severity_enum AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'maintenance_priority_enum') THEN
            CREATE TYPE maintenance_priority_enum AS ENUM ('IMMEDIATE','HIGH','PLANNED','MONITOR');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'review_status_enum') THEN
            CREATE TYPE review_status_enum AS ENUM ('PENDING','ACCEPTED','REJECTED','MODIFIED');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'data_quality_level_enum') THEN
            CREATE TYPE data_quality_level_enum AS ENUM ('EXCELLENT','GOOD','FAIR','POOR','INSUFFICIENT');
        END IF;

        END $$;
    """))

    # assets
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            asset_type asset_type_enum NOT NULL,
            fleet VARCHAR(100),
            location VARCHAR(200),
            serial_number VARCHAR(100) UNIQUE,
            manufacture_date TIMESTAMPTZ,
            total_operating_hours FLOAT NOT NULL DEFAULT 0,
            total_cycles INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_assets_asset_id ON assets (asset_id)"))

    # components
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS components (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id VARCHAR(100) NOT NULL,
            name VARCHAR(200) NOT NULL,
            component_type VARCHAR(100) NOT NULL,
            criticality VARCHAR(20) DEFAULT 'MEDIUM',
            manufacturer VARCHAR(200),
            model_number VARCHAR(100),
            install_date TIMESTAMPTZ,
            design_life_hours FLOAT,
            design_life_cycles INTEGER,
            current_operating_hours FLOAT DEFAULT 0,
            current_cycles INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT true,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_component_per_asset UNIQUE (asset_id, component_id)
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_components_asset_id ON components (asset_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_components_component_id ON components (component_id)"))

    # sensor_readings
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id UUID REFERENCES components(id) ON DELETE SET NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            sensor_type VARCHAR(50) NOT NULL,
            sensor_value FLOAT NOT NULL,
            unit VARCHAR(30),
            quality_flag VARCHAR(20),
            ingestion_batch_id VARCHAR(100)
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_asset_ts ON sensor_readings (asset_id, timestamp)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_component_ts ON sensor_readings (component_id, timestamp)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_sensor_type ON sensor_readings (sensor_type)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_timestamp ON sensor_readings (timestamp)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sensor_readings_ingestion_batch ON sensor_readings (ingestion_batch_id)"))

    # maintenance_records
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            maintenance_event_id VARCHAR(100) NOT NULL UNIQUE,
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id UUID REFERENCES components(id) ON DELETE SET NULL,
            maintenance_date TIMESTAMPTZ NOT NULL,
            maintenance_type maintenance_type_enum NOT NULL,
            description TEXT,
            technician VARCHAR(200),
            operating_hours_at_maintenance FLOAT,
            cycles_at_maintenance INTEGER,
            fault_codes JSONB,
            parts_replaced JSONB,
            outcome VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maintenance_records_asset_date ON maintenance_records (asset_id, maintenance_date)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maintenance_records_component_date ON maintenance_records (component_id, maintenance_date)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maintenance_records_event_id ON maintenance_records (maintenance_event_id)"))

    # anomaly_events
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id UUID REFERENCES components(id) ON DELETE SET NULL,
            sensor_type VARCHAR(50) NOT NULL,
            detected_at TIMESTAMPTZ NOT NULL,
            anomaly_type anomaly_type_enum NOT NULL,
            severity anomaly_severity_enum NOT NULL,
            anomaly_score FLOAT NOT NULL,
            sensor_value FLOAT,
            baseline_value FLOAT,
            deviation_pct FLOAT,
            evidence JSONB,
            is_acknowledged BOOLEAN DEFAULT false,
            pipeline_run_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_anomaly_events_component_ts ON anomaly_events (component_id, detected_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_anomaly_events_severity ON anomaly_events (severity)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_anomaly_events_pipeline_run ON anomaly_events (pipeline_run_id)"))

    # predictions
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS predictions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
            predicted_at TIMESTAMPTZ NOT NULL,
            prediction_horizon_days INTEGER NOT NULL,
            risk_score FLOAT NOT NULL,
            risk_category risk_category_enum NOT NULL,
            risk_factors JSONB,
            feature_values JSONB,
            uncertainty FLOAT,
            data_sufficiency FLOAT,
            model_version VARCHAR(50),
            layer_scores JSONB,
            pipeline_run_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_predictions_component_ts ON predictions (component_id, predicted_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_predictions_risk_category ON predictions (risk_category)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_predictions_pipeline_run ON predictions (pipeline_run_id)"))

    # readiness_assessments
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS readiness_assessments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            assessed_at TIMESTAMPTZ NOT NULL,
            status readiness_status_enum NOT NULL,
            overall_health_score FLOAT,
            primary_evidence JSONB,
            component_summary JSONB,
            data_quality_score FLOAT,
            prediction_horizon_days INTEGER DEFAULT 30,
            explanation TEXT,
            llm_explanation TEXT,
            pipeline_run_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_readiness_assessments_asset_ts ON readiness_assessments (asset_id, assessed_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_readiness_assessments_status ON readiness_assessments (status)"))

    # maintenance_recommendations
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS maintenance_recommendations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            component_id UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
            generated_at TIMESTAMPTZ NOT NULL,
            priority maintenance_priority_enum NOT NULL,
            issue_summary TEXT NOT NULL,
            evidence JSONB,
            recommended_action TEXT NOT NULL,
            urgency_days INTEGER,
            prediction_window_days INTEGER,
            risk_score FLOAT,
            data_confidence FLOAT,
            human_review_required BOOLEAN DEFAULT true,
            review_status review_status_enum DEFAULT 'PENDING',
            reviewer_notes TEXT,
            reviewed_at TIMESTAMPTZ,
            reviewed_by VARCHAR(200),
            pipeline_run_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maint_rec_priority ON maintenance_recommendations (priority)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maint_rec_asset_id ON maintenance_recommendations (asset_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_maint_rec_review_status ON maintenance_recommendations (review_status)"))

    # data_quality_reports
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS data_quality_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            report_date TIMESTAMPTZ NOT NULL,
            completeness_score FLOAT NOT NULL,
            validity_score FLOAT NOT NULL,
            consistency_score FLOAT NOT NULL,
            timeliness_score FLOAT NOT NULL,
            duplicate_rate FLOAT NOT NULL,
            missing_value_rate FLOAT NOT NULL,
            outlier_rate FLOAT NOT NULL,
            overall_score FLOAT NOT NULL,
            quality_level data_quality_level_enum NOT NULL,
            total_records INTEGER NOT NULL,
            issues_detail JSONB,
            pipeline_run_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_dqr_asset_ts ON data_quality_reports (asset_id, report_date)"))

    # audit_logs
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type VARCHAR(100) NOT NULL,
            asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
            component_id UUID,
            entity_type VARCHAR(100),
            entity_id VARCHAR(100),
            input_summary JSONB,
            calculation_details JSONB,
            result JSONB,
            model_version VARCHAR(50),
            pipeline_run_id VARCHAR(100),
            user_or_system VARCHAR(200) DEFAULT 'system'
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_audit_logs_asset_ts ON audit_logs (asset_id, timestamp)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs (event_type)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_audit_logs_pipeline_run ON audit_logs (pipeline_run_id)"))


def downgrade() -> None:
    for tbl in [
        "audit_logs", "data_quality_reports", "maintenance_recommendations",
        "readiness_assessments", "predictions", "anomaly_events",
        "maintenance_records", "sensor_readings", "components", "assets",
    ]:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))

    for enum_name in [
        "data_quality_level_enum", "review_status_enum", "maintenance_priority_enum",
        "anomaly_severity_enum", "anomaly_type_enum", "maintenance_type_enum",
        "risk_category_enum", "readiness_status_enum", "asset_type_enum",
    ]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))

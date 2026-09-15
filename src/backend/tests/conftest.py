"""
Test configuration and fixtures.

Model structure tests use SQLite in-memory for speed.
For full integration tests, set DATABASE_URL to PostgreSQL.

The production models use PostgreSQL JSONB and UUID types.
For SQLite tests, we pass string IDs and patch column types.
"""
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine, JSON, String, Text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


# ── SQLite compatibility patch ────────────────────────────────────────────────

def _patch_metadata_for_sqlite():
    """
    Patch Base.metadata in-place to replace PostgreSQL-only types
    (JSONB, UUID) with SQLite-compatible equivalents.
    This must be called before create_all().
    """
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = Text()
                col.type.impl = Text()
            elif isinstance(col.type, PG_UUID):
                col.type = String(36)


@pytest.fixture(scope="module")
def sqlite_engine():
    """SQLite in-memory engine for unit tests."""
    import app.models.models  # noqa: F401 — registers all ORM classes

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    _patch_metadata_for_sqlite()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(sqlite_engine) -> Generator[Session, None, None]:
    """Database session scoped per test function."""
    SessionTest = sessionmaker(bind=sqlite_engine)
    session = SessionTest()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def sample_asset(db_session: Session):
    """Create and persist a sample asset (unique ID per test)."""
    from app.models.models import Asset, AssetType
    uid = str(uuid.uuid4())
    asset = Asset(
        id=uid,
        asset_id=f"TEST-{uid[:8]}",
        name="Test Rotary Wing 001",
        asset_type=AssetType.ROTARY_WING,
        fleet="Test Squadron",
        total_operating_hours=1250.5,
        total_cycles=3120,
        is_active=True,
    )
    db_session.add(asset)
    db_session.commit()
    return asset


@pytest.fixture
def sample_component(db_session: Session, sample_asset):
    """Create and persist a sample component."""
    from app.models.models import Component
    comp = Component(
        id=str(uuid.uuid4()),
        asset_id=sample_asset.id,
        component_id="TEST-A001-ENG",
        name="Main Engine",
        component_type="engine",
        criticality="HIGH",
        design_life_hours=2500.0,
        current_operating_hours=1250.5,
    )
    db_session.add(comp)
    db_session.commit()
    return comp

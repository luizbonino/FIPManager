"""Engine, session factory, init_db(). No Alembic in v1 (see spec §1)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from fipm.config import get_settings
from fipm.models import Base

logger = logging.getLogger(__name__)

# v2: workshop_sessions.owner_id, fers.owner_id and knowledge_models.owner_id
# gained ondelete="SET NULL", and workshop_sessions.owner_id became nullable,
# so DELETE /api/auth/me no longer raises IntegrityError (see routers/auth.py).
# No Alembic migrations in v1: init_db() only calls create_all(), which adds
# missing tables but never alters columns/constraints on existing ones. An
# existing dev DB's on-disk FK/NOT NULL definitions predate this change, so
# delete the sqlite file (FIPM_DB_PATH) and rerun `import-data` to pick it up.
SCHEMA_VERSION = 2

settings = get_settings()

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if missing and reconcile schema_version (no migrations in v1)."""
    from fipm.models import SchemaVersionRow

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        row = db.get(SchemaVersionRow, 1)
        if row is None:
            db.add(SchemaVersionRow(id=1, version=SCHEMA_VERSION, applied_at=datetime.now(UTC)))
            db.commit()
        elif row.version < SCHEMA_VERSION:
            logger.warning(
                "schema_version %s is older than code %s; v1 changes are additive, continuing",
                row.version,
                SCHEMA_VERSION,
            )
            row.version = SCHEMA_VERSION
            row.applied_at = datetime.now(UTC)
            db.commit()
        elif row.version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema_version {row.version} is newer than this build "
                f"supports ({SCHEMA_VERSION}); refusing to start."
            )

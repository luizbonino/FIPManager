"""Engine, session factory, init_db(). No Alembic in v1 (see spec §1)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from fipm.config import get_settings
from fipm.models import Base

logger = logging.getLogger(__name__)

# v2: workshop_sessions.owner_id, fers.owner_id and knowledge_models.owner_id
# gained ondelete="SET NULL", and workshop_sessions.owner_id became nullable,
# so DELETE /api/auth/me no longer raises IntegrityError (see routers/auth.py).
# v3 (review finding 12): knowledge_models gained is_system (bool, NOT NULL,
# default False), set True only by the importer for data/knowledge-models/
# rows -- an account-deletion-anonymised published model (owner_id set to
# NULL too, see routers/auth.py) is community content, not a system model.
# No Alembic migrations in v1: init_db() only calls create_all(), which adds
# missing tables but never alters columns/constraints on existing ones. An
# existing dev DB's on-disk FK/NOT NULL definitions predate this change, so
# delete the sqlite file (FIPM_DB_PATH) and rerun `import-data` to pick it up.
# v4 (spec 05-v1-completion.md §1): `users` gains `must_change_password`
# (Boolean, NOT NULL, default False) and `privacy_accepted_version` (String,
# nullable); one new table `feedback`. Unlike v2/v3, this *is* handled
# losslessly on an existing DB: `init_db()` now also calls `_ensure_columns()`
# (below), which runs `PRAGMA table_info(<table>)` for each expected column
# and issues `ALTER TABLE ... ADD COLUMN` when it's missing -- idempotent,
# logged, and run after `create_all()` (which adds the new `feedback` table
# but never alters an existing table's columns) and before the
# schema_version reconciliation.
SCHEMA_VERSION = 4

_EXPECTED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "privacy_accepted_version", "VARCHAR"),
)

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


def _ensure_columns() -> None:
    """Idempotently add any `_EXPECTED_COLUMNS` entry missing from its table
    -- SQLite's `ALTER TABLE ... ADD COLUMN`, since `create_all()` never
    alters columns on a table that already exists (see the v4 note above)."""
    with engine.begin() as conn:
        for table, column, ddl in _EXPECTED_COLUMNS:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                logger.info("added column %s.%s", table, column)


def init_db() -> None:
    """Create tables if missing, add missing columns to existing tables, and
    reconcile schema_version (no Alembic migrations in v1)."""
    from fipm.models import SchemaVersionRow

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
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

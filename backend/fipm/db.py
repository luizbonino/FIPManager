"""Engine, session factory, init_db(). No Alembic in v1 (see spec §1)."""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError
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
# nullable); one new table `feedback`. `knowledge_models` gains `is_system`
# (v3), `changelog` and `content_sha256` (v2) -- review finding 1: an
# existing v1/v2/v3 DB is missing these NOT NULL columns entirely, so every
# query touching them would raise `OperationalError: no such column` at
# runtime, not merely carry stale FK/constraint definitions. `_ensure_columns()`
# (below) retrofits every column added since v1, with a default sane enough
# not to lose data: `is_system=0` (a pre-existing row wasn't necessarily a
# seed row -- a plain `import-data` run then reports the on-disk seed as
# "changed" for that row, per the existing content_sha256-mismatch path in
# `_import_knowledge_models`, and only rewrites `is_system`/`changelog`/
# `content_sha256` with the real values when re-run with `--force`, same as
# any other on-disk content change), `changelog='[]'` (unknown history is
# treated as empty history), `content_sha256=''` a deliberately-wrong
# placeholder that never matches a freshly computed hash, so a legacy
# user-owned KM's If-Match ETag simply misses once until its next edit
# recomputes the real hash.
#
# `init_db()` calls `_ensure_columns()` (`PRAGMA table_info(<table>)` per
# expected column, `ALTER TABLE ... ADD COLUMN` when missing) after
# `create_all()` (which adds new *tables*, like v4's `feedback`, but never
# alters columns on a table that already exists) and, critically, *before*
# the schema_version row is bumped -- if `_ensure_columns()` raises, the
# whole `_ensure_columns()` call runs inside one transaction (rolled back
# atomically) and `init_db()` propagates the exception without ever writing
# schema_version, so a half-migrated DB never reports itself as fully
# upgraded. A concurrent second process doing the same startup migration
# (e.g. two container replicas booting together) can lose the
# PRAGMA-table_info-then-ALTER race; `_ensure_columns()` catches SQLite's
# "duplicate column name" OperationalError for that one statement and treats
# it as "someone else already added it", not a startup failure.
# v5 (spec 07-mail-and-migration.md §0): one new table (`email_tokens`,
# created by `create_all()` below, no `_ensure_columns()` entry needed) and
# three nullable, additive columns -- `users.email_verified_at`,
# `fips.migrated_from`, `fips.orphaned_answers`. All nullable, so a NULL
# default for a pre-existing row is the correct "not verified / never
# migrated" value with no data loss.
# v6 (spec 08-workshop-picklists.md §0): one nullable, additive column --
# `workshop_sessions.questionnaire_refs` (JSON, `[{"id","version","label"}]`,
# 1..12 entries). NULL on a pre-v6 row means "derive the single-entry list
# from questionnaire_id/questionnaire_version" (fipm.routers.sessions), so
# no data migration/backfill is needed here.
SCHEMA_VERSION = 6

_EXPECTED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "privacy_accepted_version", "VARCHAR"),
    ("knowledge_models", "is_system", "BOOLEAN NOT NULL DEFAULT 0"),
    ("knowledge_models", "changelog", "JSON NOT NULL DEFAULT '[]'"),
    ("knowledge_models", "content_sha256", "VARCHAR NOT NULL DEFAULT ''"),
    ("users", "email_verified_at", "DATETIME"),
    ("fips", "migrated_from", "JSON"),
    ("fips", "orphaned_answers", "JSON"),
    ("workshop_sessions", "questionnaire_refs", "JSON"),
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


def _ensure_columns(bind: Engine | None = None) -> None:
    """Idempotently add any `_EXPECTED_COLUMNS` entry missing from its table
    -- SQLite's `ALTER TABLE ... ADD COLUMN`, since `create_all()` never
    alters columns on a table that already exists (see the v4 note above).

    `bind` defaults to the module-level `engine`; a test may pass its own
    isolated engine. If another process wins the race and adds the same
    column between our `PRAGMA table_info` read and our `ALTER TABLE`,
    SQLite raises `OperationalError: duplicate column name: ...` -- caught
    and logged, not fatal (review finding 1)."""
    eng = bind if bind is not None else engine
    with eng.begin() as conn:
        for table, column, ddl in _EXPECTED_COLUMNS:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            except OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    logger.info("column %s.%s already added concurrently, skipping", table, column)
                    continue
                raise
            else:
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

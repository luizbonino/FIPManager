"""AC7 (spec 05-v1-completion.md §8): starting from a hand-built
SCHEMA_VERSION-3 database (users without must_change_password /
privacy_accepted_version, no feedback table), `python -m fipm import-data`
adds both columns and the new table with no data loss, and a second run
changes nothing further. Uses a private tmp_path DB, like
test_ac03_admin_bootstrap.py, so it never touches the shared session DB.

Also review finding 1: `_EXPECTED_COLUMNS` previously omitted
`knowledge_models.is_system` (added in v3) and `.changelog`/
`.content_sha256` (added in v2), so a real v1/v2 database upgrading to this
code would hit `OperationalError: no such column` the first time any query
touched `knowledge_models`. `test_v1_db_upgrades_losslessly_and_idempotently`
and `test_v2_db_upgrades_without_touching_existing_columns` hand-build those
databases (missing table columns, not just the users ones) and check the
retrofit is lossless; `test_ensure_columns_swallows_concurrent_duplicate_column`
exercises the "two processes both add the same column" race directly against
`fipm.db._ensure_columns`."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"


def _build_v3_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (
            id VARCHAR(26) PRIMARY KEY,
            email VARCHAR NOT NULL,
            password_hash VARCHAR NOT NULL,
            display_name VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            language VARCHAR NOT NULL,
            created_at DATETIME,
            updated_at DATETIME
        );
        CREATE UNIQUE INDEX ix_users_email ON users(email);
        CREATE TABLE fips (
            id VARCHAR NOT NULL PRIMARY KEY
        );
        CREATE TABLE schema_version (
            id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at DATETIME
        );
        INSERT INTO schema_version (id, version, applied_at)
            VALUES (1, 3, '2026-01-01T00:00:00+00:00');
        INSERT INTO users
            (id, email, password_hash, display_name, role, language, created_at, updated_at)
            VALUES (
                'preexisting01', 'preexisting@example.com', 'somehash', 'Pre Existing',
                'user', 'en', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            );
        """
    )
    conn.commit()
    conn.close()


def _run_import(db_path: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(FIXTURES_DIR)
    env["FIPM_STATIC_DIR"] = str(FIXTURES_DIR / "no-such-static-dir")
    env.pop("FIPM_ADMIN_EMAIL", None)
    env.pop("FIPM_ADMIN_PASSWORD", None)
    return subprocess.run(
        [sys.executable, "-m", "fipm", "import-data"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_v3_db_upgrades_losslessly_and_idempotently(tmp_path):
    db_path = str(tmp_path / "v3_upgrade.db")
    _build_v3_db(db_path)

    r1 = _run_import(db_path)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    assert "must_change_password" in cols
    assert "privacy_accepted_version" in cols

    row = conn.execute(
        "SELECT email, display_name, must_change_password, privacy_accepted_version "
        "FROM users WHERE id = 'preexisting01'"
    ).fetchone()
    assert row is not None
    email, display_name, must_change, privacy_version = row
    assert email == "preexisting@example.com"
    assert display_name == "Pre Existing"
    assert must_change in (0, False)
    assert privacy_version is None

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "feedback" in tables
    conn.close()

    r2 = _run_import(db_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    conn2 = sqlite3.connect(db_path)
    cols2 = {row[1] for row in conn2.execute("PRAGMA table_info(users)")}
    assert cols2 == cols  # idempotent: no duplicate/changed columns
    row2 = conn2.execute("SELECT email FROM users WHERE id = 'preexisting01'").fetchone()
    assert row2 is not None
    conn2.close()


# ---------------------------------------------------------------------------
# Review finding 1: full v1 and v2 databases (knowledge_models included).
# ---------------------------------------------------------------------------

_USERS_V1_SQL = """
CREATE TABLE users (
    id VARCHAR(26) PRIMARY KEY,
    email VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    language VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
);
CREATE UNIQUE INDEX ix_users_email ON users(email);
CREATE TABLE fips (
    id VARCHAR NOT NULL PRIMARY KEY
);
CREATE TABLE schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at DATETIME
);
"""


def _build_v1_db(db_path: str) -> None:
    """No is_system/changelog/content_sha256 on knowledge_models at all (they
    didn't exist yet), no must_change_password/privacy_accepted_version on
    users, no feedback table."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        _USERS_V1_SQL
        + """
        CREATE TABLE knowledge_models (
            id VARCHAR NOT NULL,
            version VARCHAR NOT NULL,
            owner_id VARCHAR,
            visibility VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            license VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            title JSON NOT NULL,
            description JSON NOT NULL,
            content JSON NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            PRIMARY KEY (id, version)
        );
        INSERT INTO schema_version (id, version, applied_at)
            VALUES (1, 1, '2026-01-01T00:00:00+00:00');
        """
    )
    conn.execute(
        "INSERT INTO knowledge_models "
        "(id, version, owner_id, visibility, status, license, source, title, description, "
        "content, created_at, updated_at) VALUES (?, ?, NULL, 'public', 'published', 'CC0-1.0', "
        "'v1 fixture', ?, ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (
            "preexisting-v1-km",
            "1.0.0",
            json.dumps({"en": "Pre-existing v1 KM"}),
            json.dumps({"en": "A KM row from before is_system/changelog/content_sha256 existed"}),
            json.dumps({"id": "preexisting-v1-km", "version": "1.0.0"}),
        ),
    )
    conn.commit()
    conn.close()


def test_v1_db_upgrades_losslessly_and_idempotently(tmp_path):
    db_path = str(tmp_path / "v1_upgrade.db")
    _build_v1_db(db_path)

    r1 = _run_import(db_path)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    assert {"must_change_password", "privacy_accepted_version"} <= user_cols

    km_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_models)")}
    assert {"is_system", "changelog", "content_sha256"} <= km_cols

    row = conn.execute(
        "SELECT title, is_system, changelog, content_sha256 "
        "FROM knowledge_models WHERE id = 'preexisting-v1-km' AND version = '1.0.0'"
    ).fetchone()
    assert row is not None
    title, is_system, changelog, content_sha256 = row
    assert json.loads(title) == {"en": "Pre-existing v1 KM"}  # original data untouched
    assert is_system in (0, False)
    assert json.loads(changelog) == []
    assert content_sha256 == ""

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "feedback" in tables
    conn.close()

    r2 = _run_import(db_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    conn2 = sqlite3.connect(db_path)
    km_cols2 = {row[1] for row in conn2.execute("PRAGMA table_info(knowledge_models)")}
    assert km_cols2 == km_cols  # idempotent
    still_there = conn2.execute(
        "SELECT id FROM knowledge_models WHERE id = 'preexisting-v1-km'"
    ).fetchone()
    assert still_there is not None
    conn2.close()


def _build_v2_db(db_path: str) -> None:
    """changelog/content_sha256 already exist with real data (added in v2);
    only is_system (v3) and the v4 users columns/feedback table are missing.
    Checks the retrofit doesn't clobber a column that already exists."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        _USERS_V1_SQL
        + """
        CREATE TABLE knowledge_models (
            id VARCHAR NOT NULL,
            version VARCHAR NOT NULL,
            owner_id VARCHAR,
            visibility VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            license VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            title JSON NOT NULL,
            description JSON NOT NULL,
            changelog JSON NOT NULL,
            content JSON NOT NULL,
            content_sha256 VARCHAR NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            PRIMARY KEY (id, version)
        );
        INSERT INTO schema_version (id, version, applied_at)
            VALUES (1, 2, '2026-01-01T00:00:00+00:00');
        """
    )
    conn.execute(
        "INSERT INTO knowledge_models "
        "(id, version, owner_id, visibility, status, license, source, title, description, "
        "changelog, content, content_sha256, created_at, updated_at) "
        "VALUES (?, ?, NULL, 'public', 'published', 'CC0-1.0', 'v2 fixture', ?, ?, ?, ?, "
        "'real-hash-from-before-is-system-existed', "
        "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (
            "preexisting-v2-km",
            "1.0.0",
            json.dumps({"en": "Pre-existing v2 KM"}),
            json.dumps({"en": "A KM row from before is_system existed"}),
            json.dumps([{"version": "1.0.0", "date": "2026-01-01", "notes": "v2 changelog entry"}]),
            json.dumps({"id": "preexisting-v2-km", "version": "1.0.0"}),
        ),
    )
    conn.commit()
    conn.close()


def test_v2_db_upgrades_without_touching_existing_columns(tmp_path):
    db_path = str(tmp_path / "v2_upgrade.db")
    _build_v2_db(db_path)

    r1 = _run_import(db_path)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    km_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_models)")}
    assert "is_system" in km_cols

    row = conn.execute(
        "SELECT is_system, changelog, content_sha256 "
        "FROM knowledge_models WHERE id = 'preexisting-v2-km' AND version = '1.0.0'"
    ).fetchone()
    assert row is not None
    is_system, changelog, content_sha256 = row
    assert is_system in (0, False)  # only the *missing* column got a default
    # pre-existing v2 columns are untouched by ALTER TABLE ADD COLUMN:
    assert json.loads(changelog) == [
        {"version": "1.0.0", "date": "2026-01-01", "notes": "v2 changelog entry"}
    ]
    assert content_sha256 == "real-hash-from-before-is-system-existed"
    conn.close()


# ---------------------------------------------------------------------------
# Review finding 1: the concurrent-startup "duplicate column name" race.
# ---------------------------------------------------------------------------


def test_ensure_columns_swallows_concurrent_duplicate_column(tmp_path):
    """Simulates a second process winning the PRAGMA-table_info-then-ALTER
    race for one column: an event hook adds the column via a second raw
    connection right before `_ensure_columns`'s own ALTER TABLE for it runs,
    so that statement fails with SQLite's "duplicate column name" error --
    which must be swallowed, not raised, and every other expected column
    must still be added."""
    import sqlite3 as _sqlite3

    from sqlalchemy import create_engine, event

    from fipm.db import _EXPECTED_COLUMNS, _ensure_columns

    db_path = tmp_path / "race.db"
    conn = _sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE users (
            id VARCHAR(26) PRIMARY KEY,
            email VARCHAR NOT NULL
        );
        CREATE TABLE knowledge_models (
            id VARCHAR NOT NULL,
            version VARCHAR NOT NULL,
            PRIMARY KEY (id, version)
        );
        CREATE TABLE fips (
            id VARCHAR NOT NULL PRIMARY KEY
        );
        """
    )
    conn.commit()
    conn.close()

    race_engine = create_engine(f"sqlite:///{db_path}")
    raced = {"done": False}

    @event.listens_for(race_engine, "before_cursor_execute")
    def _inject_race(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if not raced["done"] and "must_change_password" in statement and "ADD COLUMN" in statement:
            raced["done"] = True
            other_process = _sqlite3.connect(str(db_path))
            other_process.execute(
                "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
            )
            other_process.commit()
            other_process.close()

    _ensure_columns(bind=race_engine)  # must not raise despite the injected race
    race_engine.dispose()

    conn2 = _sqlite3.connect(str(db_path))
    cols_by_table = {
        table: {row[1] for row in conn2.execute(f"PRAGMA table_info({table})")}
        for table in ("users", "knowledge_models", "fips")
    }
    conn2.close()

    for table, column, _ddl in _EXPECTED_COLUMNS:
        assert column in cols_by_table[table], (
            f"{table}.{column} missing after the raced _ensure_columns run"
        )
    assert raced["done"]  # the race was actually exercised

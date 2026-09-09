"""AC7 (spec 05-v1-completion.md §8): starting from a hand-built
SCHEMA_VERSION-3 database (users without must_change_password /
privacy_accepted_version, no feedback table), `python -m fipm import-data`
adds both columns and the new table with no data loss, and a second run
changes nothing further. Uses a private tmp_path DB, like
test_ac03_admin_bootstrap.py, so it never touches the shared session DB."""

from __future__ import annotations

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

"""AC3: FIPM_ADMIN_EMAIL/PASSWORD bootstrap creates exactly one admin user;
restarting with a different password leaves the stored hash unchanged and
the role still "admin". Uses subprocess + a private tmp_path DB so it never
touches the shared session DB used by the other acceptance tests.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"


def _run_import(db_path: str, admin_email: str, admin_password: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(FIXTURES_DIR)
    env["FIPM_STATIC_DIR"] = str(FIXTURES_DIR / "no-such-static-dir")
    env["FIPM_ADMIN_EMAIL"] = admin_email
    env["FIPM_ADMIN_PASSWORD"] = admin_password
    return subprocess.run(
        [sys.executable, "-m", "fipm", "import-data"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_admin_bootstrap_and_password_not_overwritten(tmp_path):
    db_path = str(tmp_path / "admin_bootstrap.db")
    email = "admin@example.com"

    r1 = _run_import(db_path, email, "first-password-123")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, role, password_hash FROM users WHERE email = ?", (email,)
    ).fetchall()
    assert len(rows) == 1
    _, role, hash1 = rows[0]
    assert role == "admin"

    r2 = _run_import(db_path, email, "second-different-password-456")
    assert r2.returncode == 0, r2.stdout + r2.stderr

    rows2 = conn.execute(
        "SELECT id, role, password_hash FROM users WHERE email = ?", (email,)
    ).fetchall()
    assert len(rows2) == 1
    _, role2, hash2 = rows2[0]
    assert role2 == "admin"
    assert hash2 == hash1
    conn.close()

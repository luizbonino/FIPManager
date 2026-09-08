"""AC4: `python -m fipm import-data` loads every fixture knowledge model and FER
seed on an empty DB; a second run changes no row and reports all-skipped.
Also verifies the importer tolerates a missing data/ directory.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"


def _base_env(db_path: str, data_dir: Path, static_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(data_dir)
    env["FIPM_STATIC_DIR"] = str(static_dir)
    env.pop("FIPM_ADMIN_EMAIL", None)
    env.pop("FIPM_ADMIN_PASSWORD", None)
    return env


def _run_import(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "fipm", "import-data"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_import_data_idempotent(tmp_path):
    db_path = str(tmp_path / "import_idempotent.db")
    env = _base_env(db_path, FIXTURES_DIR, tmp_path / "no-such-static-dir")

    r1 = _run_import(env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "knowledge_models: created=1 updated=0 skipped=0" in r1.stdout
    assert "fers: created=2 updated=0 skipped=0" in r1.stdout

    conn = sqlite3.connect(db_path)
    km_before = conn.execute("SELECT id, version, updated_at FROM knowledge_models").fetchall()
    fer_before = conn.execute("SELECT id, created_at FROM fers ORDER BY id").fetchall()
    assert len(km_before) == 1
    assert len(fer_before) == 2

    r2 = _run_import(env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "knowledge_models: created=0 updated=0 skipped=1" in r2.stdout
    assert "fers: created=0 updated=0 skipped=2" in r2.stdout

    km_after = conn.execute("SELECT id, version, updated_at FROM knowledge_models").fetchall()
    fer_after = conn.execute("SELECT id, created_at FROM fers ORDER BY id").fetchall()
    assert km_after == km_before
    assert fer_after == fer_before
    conn.close()


def test_import_data_tolerates_missing_data_dir(tmp_path):
    db_path = str(tmp_path / "empty_data.db")
    empty_data_dir = tmp_path / "no-data-here"
    env = _base_env(db_path, empty_data_dir, tmp_path / "no-such-static-dir")

    result = _run_import(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "knowledge_models: created=0 updated=0 skipped=0" in result.stdout
    assert "fers: created=0 updated=0 skipped=0" in result.stdout
    assert "fer_types: loaded=0" in result.stdout

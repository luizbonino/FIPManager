"""Review EXTRA finding: FIPM_DB_PATH and FIPM_DATA_DIR used to default to
"./fipm.db" and "./data" (relative to the process cwd), so `cd backend &&
uv run python -m fipm import-data` silently imported nothing (it looked for
backend/data instead of the repo's data/). Defaults must resolve relative to
the repo root regardless of cwd. Runs a subprocess with those two env vars
unset so pydantic-settings can't pick up the test suite's own overrides
(conftest.py sets them process-wide for every other test)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _settings_defaults_from(cwd: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("FIPM_DB_PATH", None)
    env.pop("FIPM_DATA_DIR", None)
    code = (
        "import json\n"
        "from fipm.config import Settings\n"
        "s = Settings()\n"
        "print(json.dumps({'db_path': s.db_path, 'data_dir': s.data_dir}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_defaults_resolve_to_repo_root_when_run_from_backend_dir():
    defaults = _settings_defaults_from(BACKEND_DIR)
    assert Path(defaults["db_path"]) == REPO_ROOT / "fipm.db"
    assert Path(defaults["data_dir"]) == REPO_ROOT / "data"


def test_defaults_resolve_to_repo_root_when_run_from_repo_root():
    defaults = _settings_defaults_from(REPO_ROOT)
    assert Path(defaults["db_path"]) == REPO_ROOT / "fipm.db"
    assert Path(defaults["data_dir"]) == REPO_ROOT / "data"

"""spec 10-suggested-phrases-and-other.md §2e: the importer's startup path
(`python -m fipm import-data`, run by `fipm.main`'s startup event on every
container boot -- see `fipm.importer.run_import`/`_import_knowledge_models`)
must update an unowned, unpublished (`status: "draft"`, `owner_id is None`)
knowledge model when its on-disk content changes, even though its `(id,
version)` stays the same -- i.e. it compares `content_sha256`, not just
"have I seen this version before". This exercises the real CLI entry point
(subprocess, like test_ac04_import_idempotent.py) rather than calling
`import_knowledge_model_doc` directly, so it covers the same code path a
running container hits on restart after `scripts/import-workshop-docx.py
--overwrite-draft` rewrites a shipped draft file in place."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

KM_ID = "startup-reimport-draft-km"


def _draft_doc(title: str) -> dict:
    return {
        "id": KM_ID,
        "version": "1.0.0",
        "status": "draft",
        "license": "CC0-1.0",
        "source": "Test workshop",
        "title": {"en": title},
        "description": {"en": f"{title} description"},
        "changelog": [],
        "sections": [],
    }


def _base_env(db_path: str, data_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["FIPM_DB_PATH"] = db_path
    env["FIPM_DATA_DIR"] = str(data_dir)
    env["FIPM_STATIC_DIR"] = str(data_dir / "no-such-static-dir")
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


def test_startup_reimport_updates_unowned_unpublished_draft_on_content_change(tmp_path):
    data_dir = tmp_path / "data"
    km_dir = data_dir / "knowledge-models"
    km_dir.mkdir(parents=True)
    doc_path = km_dir / f"{KM_ID}-1.0.0.json"
    doc_path.write_text(json.dumps(_draft_doc("Original title")), encoding="utf-8")

    db_path = str(tmp_path / "startup_reimport.db")
    env = _base_env(db_path, data_dir)

    r1 = _run_import(env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "knowledge_models: created=1 updated=0 skipped=0" in r1.stdout

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT title, owner_id, is_system FROM knowledge_models WHERE id = ?", (KM_ID,)
    ).fetchone()
    assert "Original title" in row[0]
    assert row[1] is None  # unowned
    assert row[2] == 0  # not a system model (status draft)

    # Same (id, version), content changed on disk -- simulates
    # scripts/import-workshop-docx.py --overwrite-draft rewriting the file
    # before the container's next restart.
    doc_path.write_text(json.dumps(_draft_doc("Updated title")), encoding="utf-8")

    r2 = _run_import(env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "knowledge_models: created=0 updated=1 skipped=0" in r2.stdout

    title_after = conn.execute(
        "SELECT title FROM knowledge_models WHERE id = ?", (KM_ID,)
    ).fetchone()[0]
    assert "Updated title" in title_after

    # A third run with no further on-disk change is a no-op (idempotent).
    r3 = _run_import(env)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "knowledge_models: created=0 updated=0 skipped=1" in r3.stdout
    conn.close()


def test_startup_reimport_never_overwrites_a_claimed_draft(tmp_path):
    """The same startup path must still leave a facilitator-claimed
    (owner_id set) draft alone even when the shipped file changes --
    unowned-only sync, not a blanket "draft always wins"."""
    data_dir = tmp_path / "data"
    km_dir = data_dir / "knowledge-models"
    km_dir.mkdir(parents=True)
    doc_path = km_dir / f"{KM_ID}-1.0.0.json"
    doc_path.write_text(json.dumps(_draft_doc("Original title")), encoding="utf-8")

    db_path = str(tmp_path / "startup_reimport_claimed.db")
    env = _base_env(db_path, data_dir)

    r1 = _run_import(env)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE knowledge_models SET owner_id = ? WHERE id = ?", ("some-facilitator-id", KM_ID)
    )
    conn.commit()

    doc_path.write_text(json.dumps(_draft_doc("Changed on disk again")), encoding="utf-8")

    r2 = _run_import(env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "knowledge_models: created=0 updated=0 skipped=1" in r2.stdout

    title_after = conn.execute(
        "SELECT title FROM knowledge_models WHERE id = ?", (KM_ID,)
    ).fetchone()[0]
    assert "Original title" in title_after
    conn.close()

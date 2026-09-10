"""spec 08-workshop-picklists.md §6 AC13:
- `GET /api/sessions/{id}/export.csv` for a two-area session has `area` as
  its third column, the right label per row, and the 26 FIP columns after
  it; `export.json` carries `session.questionnaireRefs` and a per-FIP
  `area`.
- `init_db()` on a v5 SQLite file adds `questionnaire_refs` and reports
  version 6."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fipm.db import SCHEMA_VERSION
from fipm.exporters import CSV_HEADER

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Session CSV/JSON `area` (two-area session)
# ---------------------------------------------------------------------------


def _register(client, email: str) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text


def _publish_fork(client, new_id: str, title_en: str) -> None:
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": new_id})
    assert fork.status_code == 201, fork.text
    client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"title": {"en": title_en}})
    client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"visibility": "public"})
    pub = client.post(f"/api/knowledge-models/{new_id}/1.0.0/publish", json={"notes": "go"})
    assert pub.status_code == 200, pub.text


def test_two_area_session_csv_and_json_carry_area(client_factory):
    owner = client_factory()
    _register(owner, "ac08-13@example.com")
    _publish_fork(owner, "ac0813-area-a", "Area A")
    _publish_fork(owner, "ac0813-area-b", "Area B")

    session = owner.post(
        "/api/sessions",
        json={
            "title": "Two area session",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": "ac0813-area-a", "version": "1.0.0", "label": {"en": "Area A label"}},
                {"id": "ac0813-area-b", "version": "1.0.0", "label": {"en": "Area B label"}},
            ],
        },
    ).json()

    participant_a = client_factory()
    fip_a = participant_a.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "ac0813-area-a", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": "Group A"},
        },
    )
    assert fip_a.status_code == 201, fip_a.text

    participant_b = client_factory()
    fip_b = participant_b.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "ac0813-area-b", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "community": {"name": "Group B"},
        },
    )
    assert fip_b.status_code == 201, fip_b.text

    csv_resp = owner.get(f"/api/sessions/{session['id']}/export.csv")
    assert csv_resp.status_code == 200
    raw = csv_resp.content.decode("utf-8-sig")
    lines = [line for line in raw.split("\r\n") if line]
    header = lines[0].split(",")
    assert header[:3] == ["session_id", "fip_title", "area"]
    assert header[3:] == CSV_HEADER

    rows_by_title = {}
    for line in lines[1:]:
        cells = line.split(",")
        rows_by_title.setdefault(cells[1], set()).add(cells[2])
    assert rows_by_title["Group A"] == {"Area A label"}
    assert rows_by_title["Group B"] == {"Area B label"}

    json_resp = owner.get(f"/api/sessions/{session['id']}/export.json")
    assert json_resp.status_code == 200
    doc = json_resp.json()
    assert [r["id"] for r in doc["session"]["questionnaireRefs"]] == [
        "ac0813-area-a",
        "ac0813-area-b",
    ]
    fip_docs_by_title = {(f["fip"]["community"] or {}).get("name"): f for f in doc["fips"]}
    assert fip_docs_by_title["Group A"]["area"]["id"] == "ac0813-area-a"
    assert fip_docs_by_title["Group A"]["area"]["label"] == {"en": "Area A label"}
    assert fip_docs_by_title["Group B"]["area"]["id"] == "ac0813-area-b"


# ---------------------------------------------------------------------------
# init_db() on a v5 SQLite file
# ---------------------------------------------------------------------------

_V5_SCHEMA_SQL = """
CREATE TABLE users (
    id VARCHAR(26) PRIMARY KEY,
    email VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    language VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    must_change_password BOOLEAN NOT NULL DEFAULT 0,
    privacy_accepted_version VARCHAR,
    email_verified_at DATETIME
);
CREATE UNIQUE INDEX ix_users_email ON users(email);
CREATE TABLE knowledge_models (
    id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    owner_id VARCHAR,
    visibility VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    license VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT 0,
    title JSON NOT NULL,
    description JSON NOT NULL,
    changelog JSON NOT NULL,
    content JSON NOT NULL,
    content_sha256 VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (id, version)
);
CREATE TABLE workshop_sessions (
    id VARCHAR NOT NULL PRIMARY KEY,
    join_code VARCHAR(6) NOT NULL,
    owner_id VARCHAR,
    questionnaire_id VARCHAR NOT NULL,
    questionnaire_version VARCHAR NOT NULL,
    default_language VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
);
CREATE UNIQUE INDEX ix_sessions_join_code ON workshop_sessions(join_code);
CREATE TABLE fips (
    id VARCHAR NOT NULL PRIMARY KEY,
    owner_id VARCHAR,
    session_id VARCHAR,
    edit_token_hash VARCHAR(64),
    visibility VARCHAR NOT NULL,
    questionnaire_id VARCHAR NOT NULL,
    questionnaire_version VARCHAR NOT NULL,
    title VARCHAR,
    community JSON,
    related_dmps JSON,
    answers JSON NOT NULL,
    language VARCHAR NOT NULL,
    license VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    migrated_from JSON,
    orphaned_answers JSON
);
CREATE TABLE schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at DATETIME
);
INSERT INTO schema_version (id, version, applied_at)
    VALUES (1, 5, '2026-01-01T00:00:00+00:00');
INSERT INTO workshop_sessions
    (id, join_code, owner_id, questionnaire_id, questionnaire_version, default_language,
     title, status, created_at, updated_at)
    VALUES (
        'preexisting-session-01', 'ABC123', NULL, 'test-km', '1.0.0', 'en',
        'A pre-v6 session', 'open', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
    );
"""


def _build_v5_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_V5_SCHEMA_SQL)
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


def test_v5_db_upgrades_to_v6_losslessly_and_idempotently(tmp_path):
    db_path = str(tmp_path / "v5_upgrade.db")
    _build_v5_db(db_path)

    r1 = _run_import(db_path)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    conn = sqlite3.connect(db_path)
    session_cols = {row[1] for row in conn.execute("PRAGMA table_info(workshop_sessions)")}
    assert "questionnaire_refs" in session_cols

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    # spec 11-nanopub-network.md §4: SCHEMA_VERSION moved 6 -> 7; this test
    # is about the v5->v6 questionnaire_refs retrofit specifically, so it
    # asserts against the current constant rather than a hardcoded number.
    assert version == SCHEMA_VERSION

    row = conn.execute(
        "SELECT title, questionnaire_id, questionnaire_refs "
        "FROM workshop_sessions WHERE id = 'preexisting-session-01'"
    ).fetchone()
    assert row is not None
    title, questionnaire_id, refs = row
    assert title == "A pre-v6 session"  # original data untouched
    assert questionnaire_id == "test-km"
    assert refs is None  # additive-only: no backfill, derived at read time
    conn.close()

    r2 = _run_import(db_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    conn2 = sqlite3.connect(db_path)
    session_cols2 = {row[1] for row in conn2.execute("PRAGMA table_info(workshop_sessions)")}
    assert session_cols2 == session_cols  # idempotent
    still_there = conn2.execute(
        "SELECT id FROM workshop_sessions WHERE id = 'preexisting-session-01'"
    ).fetchone()
    assert still_there is not None
    conn2.close()

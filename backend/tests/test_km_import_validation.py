"""AC6 (spec 04 §6): POST /api/knowledge-models/import validates the document
via `fipm.km_content.validate_content` (duplicate question id, missing en);
importing the unmodified real gofair-fip-mini-1.0.0.json succeeds as a
private draft owned by the caller and leaves the system row untouched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.models import KnowledgeModel

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _base_document() -> dict:
    return {
        "id": "ignored-client-id",
        "version": "9.9.9",
        "status": "published",
        "license": "CC0-1.0",
        "source": "Test",
        "title": {"en": "Import test"},
        "description": {"en": "Import test description"},
        "changelog": [],
        "sections": [
            {
                "id": "sec1",
                "title": {"en": "Section 1"},
                "questions": [
                    {
                        "id": "dup-id",
                        "text": {"en": "First"},
                        "required": False,
                        "allowMultiple": True,
                    },
                    {
                        "id": "dup-id",
                        "text": {"en": "Second"},
                        "required": False,
                        "allowMultiple": True,
                    },
                ],
            }
        ],
    }


def test_import_duplicate_question_id_returns_invalid_content(client):
    _register(client, "import-dup-id@example.com")
    doc = _base_document()
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"] == "invalid_content"
    assert body["errors"][0] == {
        "path": "sections[0].questions[1].id",
        "code": "duplicate_question_id",
        "message": body["errors"][0]["message"],
    }


def test_import_missing_en_returns_missing_en(client):
    _register(client, "import-missing-en@example.com")
    doc = _base_document()
    doc["sections"][0]["questions"] = [
        {"id": "q1", "text": {"pt-PT": "Pergunta"}, "required": False, "allowMultiple": True}
    ]
    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["detail"] == "invalid_content"
    hit = next(e for e in body["errors"] if e["code"] == "missing_en")
    assert hit["path"] == "sections[0].questions[0].text"


@pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)
def test_import_unmodified_real_gofair_file_succeeds(client, db_session):
    user_id = _register(client, "import-real-gofair@example.com")
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))

    before_system_row = db_session.get(KnowledgeModel, ("gofair-fip-mini", "1.0.0"))
    before_sha = before_system_row.content_sha256 if before_system_row else None

    r = client.post("/api/knowledge-models/import", json={"document": doc})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ownerId"] == user_id
    assert body["status"] == "draft"
    assert body["visibility"] == "private"
    assert body["version"] == "1.0.0"
    assert body["id"] != "gofair-fip-mini"

    db_session.expire_all()
    after_system_row = db_session.get(KnowledgeModel, ("gofair-fip-mini", "1.0.0"))
    if before_system_row is not None:
        assert after_system_row.content_sha256 == before_sha

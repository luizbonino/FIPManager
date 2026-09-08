"""AC1 (spec 04 §6): forking the real GO FAIR system model returns a private
draft owned by the caller that inherits CC-BY-SA-4.0 + the spec 00 §6
attribution string automatically; the system row is never mutated. A second
fork without `newId` gets the `-fork-2` suffix (spec 04 §1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fipm.config import Settings
from fipm.importer import ImportSummary, _import_knowledge_models
from fipm.models import KnowledgeModel

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_KM_PATH = REAL_DATA_DIR / "knowledge-models" / "gofair-fip-mini-1.0.0.json"

pytestmark = pytest.mark.skipif(
    not REAL_KM_PATH.is_file(),
    reason="data/knowledge-models/gofair-fip-mini-1.0.0.json not present",
)

ATTRIBUTION = (
    "FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, "
    "Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0."
)


def _import_real_gofair(db_session, settings) -> None:
    real_settings = Settings(
        data_dir=str(REAL_DATA_DIR), db_path=settings.db_path, base_url=settings.base_url
    )
    _import_knowledge_models(db_session, real_settings, ImportSummary(), force=False)


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_fork_real_gofair_model_inherits_licence_and_attribution(client, db_session, settings):
    _import_real_gofair(db_session, settings)
    doc = json.loads(REAL_KM_PATH.read_text(encoding="utf-8"))

    user_id = _register(client, "fork-licence-user@example.com")

    before = db_session.get(KnowledgeModel, ("gofair-fip-mini", "1.0.0"))
    before_sha = before.content_sha256
    before_owner = before.owner_id
    before_updated = before.updated_at

    r = client.post("/api/knowledge-models/gofair-fip-mini/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "gofair-fip-mini-fork"
    assert body["ownerId"] == user_id
    assert body["version"] == "1.0.0"
    assert body["status"] == "draft"
    assert body["visibility"] == "private"
    assert body["license"] == "CC-BY-SA-4.0"
    assert body["content"]["forkedFrom"] == {"id": "gofair-fip-mini", "version": "1.0.0"}
    assert body["content"]["attribution"] == ATTRIBUTION
    assert body["content"]["sections"] == doc["sections"]

    db_session.expire_all()
    after = db_session.get(KnowledgeModel, ("gofair-fip-mini", "1.0.0"))
    assert after.content_sha256 == before_sha
    assert after.owner_id == before_owner
    assert after.updated_at == before_updated

    r2 = client.post("/api/knowledge-models/gofair-fip-mini/1.0.0/fork", json={})
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == "gofair-fip-mini-fork-2"


def test_fork_of_cc0_model_does_not_force_cc_by_sa(client):
    _register(client, "fork-licence-cc0@example.com")
    r = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["license"] == "CC0-1.0"
    assert "attribution" not in body["content"]

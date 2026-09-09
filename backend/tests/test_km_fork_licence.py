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
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
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


def _make_km(db_session, *, id_, version, license_, content_license, status="published"):
    from fipm.models import KnowledgeModel

    km = KnowledgeModel(
        id=id_,
        version=version,
        owner_id=None,
        visibility="public",
        status=status,
        license=license_,
        source="test",
        title={"en": id_},
        description={"en": id_},
        changelog=[],
        content={
            "id": id_,
            "version": version,
            "status": status,
            "license": content_license,
            "title": {"en": id_},
            "description": {"en": id_},
            "sections": [],
        },
        content_sha256="x",
    )
    db_session.add(km)
    db_session.commit()
    return km


def test_fork_content_license_mirrors_row_license_for_cc_by_sa(client, db_session):
    """Review finding 5: content.license must be set to the row's final
    licence even when the source row's own `content.license` field is stale
    (e.g. from data predating this fix) -- not just the row's `license`
    column, which already gets overridden to "CC-BY-SA-4.0" here."""
    _make_km(
        db_session,
        id_="fork-license-stale-ccbysa",
        version="1.0.0",
        license_="CC-BY-SA-3.0",
        content_license="totally-different-stale-value",
    )
    _register(client, "fork-licence-stale-ccbysa@example.com")
    r = client.post("/api/knowledge-models/fork-license-stale-ccbysa/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["license"] == "CC-BY-SA-4.0"
    assert body["content"]["license"] == "CC-BY-SA-4.0"


def test_fork_content_license_mirrors_row_license_for_other_licences(client, db_session):
    _make_km(
        db_session,
        id_="fork-license-stale-mit",
        version="1.0.0",
        license_="MIT",
        content_license="CC0-1.0",
    )
    _register(client, "fork-licence-stale-mit@example.com")
    r = client.post("/api/knowledge-models/fork-license-stale-mit/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["license"] == "MIT"
    assert body["content"]["license"] == "MIT"


def test_fork_always_starts_at_version_1_0_0(client, db_session):
    """Review finding 11 / spec 04 §1: all three ways a user model starts
    (fork, scratch, import) create version "1.0.0", regardless of the
    source's own version."""
    _make_km(
        db_session,
        id_="fork-source-high-version",
        version="2.3.1",
        license_="CC0-1.0",
        content_license="CC0-1.0",
    )
    _register(client, "fork-high-version@example.com")
    r = client.post("/api/knowledge-models/fork-source-high-version/2.3.1/fork", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == "1.0.0"
    assert body["content"]["version"] == "1.0.0"

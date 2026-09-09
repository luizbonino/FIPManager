"""Review finding 1: POST /fips, POST /sessions and POST /fips/import must
require the referenced knowledge model to be `status="published"` and
readable by the caller (`can_read`), not merely to exist. A draft KM, or a
private KM the caller cannot read, returns 404 `questionnaire_not_found`
even for the KM's own owner (draft is never enough on its own)."""

from __future__ import annotations

from fipm.models import KnowledgeModel


def _register(client, email, display_name="U"):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": display_name,
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def _make_km(db_session, *, id_, version, owner_id, status, visibility):
    km = KnowledgeModel(
        id=id_,
        version=version,
        owner_id=owner_id,
        visibility=visibility,
        status=status,
        license="CC0-1.0",
        source="test",
        title={"en": id_},
        description={"en": id_},
        changelog=[],
        content={"id": id_, "version": version, "sections": []},
        content_sha256="x",
    )
    db_session.add(km)
    db_session.commit()
    return km


def test_create_fip_rejects_draft_km_even_for_its_owner(client, db_session):
    owner_id = _register(client, "kmgate-draft-owner@example.com")
    _make_km(
        db_session,
        id_="kmgate-draft",
        version="1.0.0",
        owner_id=owner_id,
        status="draft",
        visibility="private",
    )
    r = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "kmgate-draft", "version": "1.0.0"}}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "questionnaire_not_found"


def test_create_fip_rejects_private_km_not_owned_by_caller(client, client_factory, db_session):
    owner_id = _register(client_factory(), "kmgate-priv-owner@example.com")
    _make_km(
        db_session,
        id_="kmgate-private",
        version="1.0.0",
        owner_id=owner_id,
        status="published",
        visibility="private",
    )
    _register(client, "kmgate-other@example.com")
    r = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "kmgate-private", "version": "1.0.0"}}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "questionnaire_not_found"


def test_create_session_rejects_draft_km(client, db_session):
    owner_id = _register(client, "kmgate-session-owner@example.com")
    _make_km(
        db_session,
        id_="kmgate-session-draft",
        version="1.0.0",
        owner_id=owner_id,
        status="draft",
        visibility="private",
    )
    r = client.post(
        "/api/sessions",
        json={
            "title": "t",
            "questionnaireRef": {"id": "kmgate-session-draft", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "questionnaire_not_found"


def test_import_fip_rejects_draft_km(client, db_session):
    owner_id = _register(client, "kmgate-import-owner@example.com")
    _make_km(
        db_session,
        id_="kmgate-import-draft",
        version="1.0.0",
        owner_id=owner_id,
        status="draft",
        visibility="private",
    )
    doc = {
        "exportVersion": 1,
        "fip": {},
        "questionnaireRef": {"id": "kmgate-import-draft", "version": "1.0.0"},
        "answers": [],
    }
    r = client.post("/api/fips/import", json=doc)
    assert r.status_code == 404
    assert r.json()["detail"] == "questionnaire_not_found"


def test_create_fip_still_works_against_published_public_km(client):
    _register(client, "kmgate-happy@example.com")
    r = client.post("/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}})
    assert r.status_code == 201

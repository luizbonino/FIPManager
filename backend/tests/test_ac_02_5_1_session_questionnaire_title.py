"""spec 02-core-flows.md §5.1 / §8 item 1: GET /api/sessions/by-code/{joinCode}
carries `questionnaireTitle` (the knowledge model's own `title` LangMap),
alongside the existing fields; an unknown code still 404s.

Review finding 4: this lookup is public and unauthenticated, so it must not
leak a private knowledge model's title through the session's public join
code -- `questionnaireTitle` is only populated when the KM would itself be
readable by an anonymous caller (published and public/link visibility)."""

from __future__ import annotations

from fipm.models import KnowledgeModel


def test_session_by_code_includes_questionnaire_title(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "qtitle-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = client.post(
        "/api/sessions",
        json={
            "title": "Title workshop",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    r = client.get(f"/api/sessions/by-code/{session['joinCode']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == session["id"]
    assert body["status"] == "open"
    assert body["facilitatorName"] == "F"
    # test-km's title fixture carries "en" and "pt-BR" only (no "pt-PT").
    assert body["questionnaireTitle"]["en"] == "Test knowledge model"
    assert body["questionnaireTitle"]["pt-BR"] == "Modelo de conhecimento de teste"


def test_session_by_code_unknown_code_is_404(client):
    r = client.get("/api/sessions/by-code/ZZZZZZ")
    assert r.status_code == 404


def test_session_by_code_omits_title_for_private_questionnaire(client, db_session):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "qtitle-private-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "PrivOwner",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    owner_id = reg.json()["id"]

    km = KnowledgeModel(
        id="qtitle-private-km",
        version="1.0.0",
        owner_id=owner_id,
        visibility="private",
        status="published",
        license="CC0-1.0",
        source="test",
        title={"en": "Secret questionnaire"},
        description={"en": "secret"},
        changelog=[],
        content={"id": "qtitle-private-km", "version": "1.0.0", "sections": []},
        content_sha256="z",
    )
    db_session.add(km)
    db_session.commit()

    # The owner can create a session against their own private KM.
    session = client.post(
        "/api/sessions",
        json={
            "title": "Private title workshop",
            "questionnaireRef": {"id": "qtitle-private-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    r = client.get(f"/api/sessions/by-code/{session['joinCode']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == session["id"]
    # The KM is private, so the public join-code lookup must not leak its
    # title, even though the KM itself exists and is published.
    assert body["questionnaireTitle"] == {}

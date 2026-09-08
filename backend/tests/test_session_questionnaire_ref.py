"""Review finding 7: creating a FIP inside a session must use the session's
own questionnaire_id/version; a body questionnaireRef that disagrees with the
session's is a 400, not a silent override or an accepted mismatch."""

from __future__ import annotations

from fipm.models import KnowledgeModel


def _make_session(client_factory, owner_email):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={"email": owner_email, "password": "correcthorsebattery", "displayName": "F"},
    )
    r = owner.post(
        "/api/sessions",
        json={
            "title": "qref session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_mismatched_questionnaire_ref_in_session_is_400(client, client_factory, db_session):
    session = _make_session(client_factory, "qref-owner@example.com")

    other_km = KnowledgeModel(
        id="qref-other-km",
        version="1.0.0",
        owner_id=None,
        visibility="public",
        status="published",
        license="CC0-1.0",
        source="test",
        title={"en": "other"},
        description={"en": "other"},
        changelog=[],
        content={"id": "qref-other-km", "version": "1.0.0", "sections": []},
        content_sha256="z",
    )
    db_session.add(other_km)
    db_session.commit()

    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "qref-other-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "questionnaire_ref_mismatch"


def test_matching_questionnaire_ref_in_session_still_works(client, client_factory):
    session = _make_session(client_factory, "qref-owner2@example.com")
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert r.status_code == 201
    assert r.json()["questionnaireId"] == "test-km"

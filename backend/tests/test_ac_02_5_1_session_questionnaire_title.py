"""spec 02-core-flows.md §5.1 / §8 item 1: GET /api/sessions/by-code/{joinCode}
carries `questionnaireTitle` (the knowledge model's own `title` LangMap),
alongside the existing fields; an unknown code still 404s."""

from __future__ import annotations


def test_session_by_code_includes_questionnaire_title(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "qtitle-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
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

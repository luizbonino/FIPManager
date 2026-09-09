"""Review finding 3: GET /api/me/fips and GET /api/sessions/{id}/fips used
to always return `summary.totalQuestions: null` (and, by extension,
unfiltered `answeredQuestions`/`byStatus`) because neither endpoint passed
its knowledge model through to `fip_out_dict`, unlike GET /api/fips/{id}.
Both now fetch the distinct knowledge model(s) referenced by the listed
FIPs once and pass the same summary a single-FIP GET would."""

from __future__ import annotations

import itertools

_EMAILS = (f"list-total-q-{i}@example.com" for i in itertools.count())


def test_me_fips_list_has_total_questions(client):
    client.post(
        "/api/auth/register",
        json={
            "email": next(_EMAILS),
            "password": "correcthorsebattery",
            "displayName": "L",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    fip_id = created.json()["id"]

    listing = client.get("/api/me/fips")
    assert listing.status_code == 200
    item = next(i for i in listing.json()["items"] if i["id"] == fip_id)
    assert item["summary"]["totalQuestions"] == 2
    assert item["summary"]["answeredQuestions"] == 1


def test_session_fips_list_has_total_questions(client, client_factory):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": next(_EMAILS),
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "total-questions session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    fip = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    ).json()

    listing = facilitator.get(f"/api/sessions/{session['id']}/fips")
    assert listing.status_code == 200
    item = next(i for i in listing.json()["items"] if i["id"] == fip["id"])
    assert item["summary"]["totalQuestions"] == 2
    assert item["summary"]["answeredQuestions"] == 1

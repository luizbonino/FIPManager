"""spec 08-workshop-picklists.md §6 AC6: `PATCH /api/fips/{id}` with
`notApplicable: true` and a declaration -> 422 `not_applicable_with_declarations`;
with the flag alone -> 200, and `summary.answeredQuestions` counts that
question."""

from __future__ import annotations


def _create_fip(client, email):
    client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "D",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_not_applicable_with_declarations_is_422(client):
    fip_id = _create_fip(client, "ac08-06-a@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "notApplicable": True,
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ]
        },
    )
    assert r.status_code == 422


def test_not_applicable_alone_is_200_and_counts_as_answered(client):
    fip_id = _create_fip(client, "ac08-06-b@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={"answers": [{"questionId": "F1-metadata", "notApplicable": True}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["answeredQuestions"] == 1
    assert body["summary"]["notApplicable"] == 1
    # test-km has 2 questions; only F1-metadata is answered (as N/A).
    assert body["summary"]["totalQuestions"] == 2
    answer = next(a for a in body["answers"] if a["questionId"] == "F1-metadata")
    assert answer["notApplicable"] is True
    assert answer["declarations"] == []


def test_not_applicable_false_is_never_stored(client):
    """spec §2.1: `notApplicable: false` is dropped from the payload, so the
    stored `answers` blob is byte-identical to one that never mentioned it."""
    fip_id = _create_fip(client, "ac08-06-c@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={"answers": [{"questionId": "F1-metadata", "notApplicable": False}]},
    )
    assert r.status_code == 200, r.text

    from fipm.db import SessionLocal
    from fipm.models import Fip

    with SessionLocal() as db:
        fip = db.get(Fip, fip_id)
        stored_answer = next(a for a in fip.answers if a["questionId"] == "F1-metadata")
        assert "notApplicable" not in stored_answer

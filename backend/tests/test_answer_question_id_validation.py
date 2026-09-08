"""Review finding 5: POST /fips and PATCH /fips/{id} must validate every
answers[].questionId against the referenced knowledge model's actual question
ids, returning 400 `unknown_question_id` rather than silently storing an
answer to a question that doesn't exist."""

from __future__ import annotations


def test_create_fip_rejects_unknown_question_id(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "qid-create@example.com",
            "password": "correcthorsebattery",
            "displayName": "Q",
        },
    )
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "does-not-exist",
                    "declarations": [{"ferFreeText": "x", "status": "current"}],
                }
            ],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_question_id"


def test_create_fip_accepts_known_question_id(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "qid-create-ok@example.com",
            "password": "correcthorsebattery",
            "displayName": "Q",
        },
    )
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferFreeText": "x", "status": "current"}],
                }
            ],
        },
    )
    assert r.status_code == 201


def test_patch_fip_rejects_unknown_question_id(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "qid-patch@example.com",
            "password": "correcthorsebattery",
            "displayName": "Q",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    fip_id = created.json()["id"]

    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "still-not-a-real-question",
                    "declarations": [{"ferFreeText": "x", "status": "current"}],
                }
            ]
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown_question_id"

    # The FIP's answers must be unchanged after the rejected patch.
    unchanged = client.get(f"/api/fips/{fip_id}")
    assert unchanged.json()["answers"] == []

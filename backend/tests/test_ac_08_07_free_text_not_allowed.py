"""spec 08-workshop-picklists.md §6 AC7: `ferFreeText` on a question with
`allowFreeText: false` -> 422 `free_text_not_allowed`; the same payload on a
question with the field absent -> 200."""

from __future__ import annotations


def _register(client, email: str) -> None:
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


def _publish_model_with_two_questions(client) -> str:
    created = client.post("/api/knowledge-models", json={"title": {"en": "No free text model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]
    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    sections = [
        {
            "id": "sec1",
            "title": {"en": "Section 1"},
            "questions": [
                {
                    "id": "q-no-free-text",
                    "text": {"en": "Restricted question"},
                    "ferType": "identifier-service",
                    "allowFreeText": False,
                    "suggestedFerIds": ["https://w3id.org/np/doi"],
                },
                {
                    "id": "q-default",
                    "text": {"en": "Ordinary question"},
                    "ferType": "identifier-service",
                },
            ],
        }
    ]
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections},
    )
    assert put1.status_code == 200, put1.text
    pub1 = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert pub1.status_code == 200, pub1.text
    return km_id


def test_free_text_rejected_when_not_allowed_accepted_when_field_absent(client):
    _register(client, "ac08-07@example.com")
    km_id = _publish_model_with_two_questions(client)

    fip = client.post("/api/fips", json={"questionnaireRef": {"id": km_id, "version": "1.0.0"}})
    assert fip.status_code == 201, fip.text
    fip_id = fip.json()["id"]

    rejected = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "q-no-free-text",
                    "declarations": [{"ferFreeText": "my own wording", "status": "current"}],
                }
            ]
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "free_text_not_allowed"

    # The identical payload against a question with allowFreeText absent (=
    # default true) is accepted.
    accepted = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "q-default",
                    "declarations": [{"ferFreeText": "my own wording", "status": "current"}],
                }
            ]
        },
    )
    assert accepted.status_code == 200, accepted.text

    # Catalogue-only on the restricted question still works.
    catalogue_only = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "q-no-free-text",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ]
        },
    )
    assert catalogue_only.status_code == 200, catalogue_only.text


def test_free_text_rejected_on_post_fips_create(client):
    """The same rule applies on the create path (`POST /api/fips`), not
    only PATCH."""
    _register(client, "ac08-07b@example.com")
    km_id = _publish_model_with_two_questions(client)
    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "q-no-free-text",
                    "declarations": [{"ferFreeText": "nope", "status": "current"}],
                }
            ],
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "free_text_not_allowed"

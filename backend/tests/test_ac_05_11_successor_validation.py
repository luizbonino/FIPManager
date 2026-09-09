"""AC11 (spec 05-v1-completion.md §8): a declaration with successorFerId and
status != "planned-replacement" returns 422, as does one with both successor
fields set; a planned-replacement declaration with neither still saves."""

from __future__ import annotations

PRIVACY_VERSION = "test-v1"


def _create_fip(client, email):
    client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "D",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_successor_id_without_planned_replacement_status_422(client):
    fip_id = _create_fip(client, "ac05-11-a@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "current",
                            "successorFerId": "https://w3id.org/np/doi2",
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 422


def test_successor_both_fields_set_422(client):
    fip_id = _create_fip(client, "ac05-11-b@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "planned-replacement",
                            "successorFerId": "https://w3id.org/np/doi2",
                            "successorFreeText": "Also free text",
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 422


def test_planned_replacement_without_successor_saves(client):
    fip_id = _create_fip(client, "ac05-11-c@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {"ferId": "https://w3id.org/np/doi", "status": "planned-replacement"}
                    ],
                }
            ]
        },
    )
    assert r.status_code == 200


def test_planned_replacement_with_successor_free_text_saves(client):
    fip_id = _create_fip(client, "ac05-11-d@example.com")
    r = client.patch(
        f"/api/fips/{fip_id}",
        json={
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {
                            "ferId": "https://w3id.org/np/doi",
                            "status": "planned-replacement",
                            "successorFreeText": "Our new in-house registry",
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 200
    decl = r.json()["answers"][0]["declarations"][0]
    assert decl["successorFreeText"] == "Our new in-house registry"

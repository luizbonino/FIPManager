"""AC11 (spec 05-v1-completion.md §8): a declaration with successorFerId and
status != "planned-replacement" returns 422, as does one with both successor
fields set; a planned-replacement declaration with neither still saves.

Review finding 8 also lives here: ferId/successorFerId must be http(s)://
or urn: IRIs with no whitespace/control characters (422 invalid_fer_iri),
and successorFerId must not equal ferId within the same declaration (422
successor_same_as_fer)."""

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


def test_fer_id_must_be_an_iri_422(client):
    """Review finding 8: ferId must be an http(s):// or urn: IRI -- a bare
    word, a non-http(s)/urn scheme, or anything with embedded whitespace or
    control characters is 422."""
    fip_id = _create_fip(client, "ac05-11-e@example.com")
    for bad_fer_id in (
        "not-an-iri",
        "ftp://example.org/fers/x",
        "https://example.org/has space",
        "https://example.org/has\ttab",
        "https://example.org/has\x00null",
    ):
        r = client.patch(
            f"/api/fips/{fip_id}",
            json={
                "answers": [
                    {
                        "questionId": "F1-metadata",
                        "declarations": [{"ferId": bad_fer_id, "status": "current"}],
                    }
                ]
            },
        )
        assert r.status_code == 422, f"{bad_fer_id!r} should be rejected, got {r.status_code}"


def test_fer_id_accepts_http_https_and_urn_iris(client):
    fip_id = _create_fip(client, "ac05-11-f@example.com")
    for good_fer_id in (
        "https://w3id.org/np/doi",
        "http://example.org/fers/plain-http",
        "urn:example:fer:123",
    ):
        r = client.patch(
            f"/api/fips/{fip_id}",
            json={
                "answers": [
                    {
                        "questionId": "F1-metadata",
                        "declarations": [{"ferId": good_fer_id, "status": "current"}],
                    }
                ]
            },
        )
        assert r.status_code == 200, f"{good_fer_id!r} should be accepted, got {r.text}"


def test_successor_fer_id_equal_to_fer_id_422(client):
    """Review finding 8: successorFerId pointing right back at the same
    ferId within one declaration isn't a replacement."""
    fip_id = _create_fip(client, "ac05-11-g@example.com")
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
                            "successorFerId": "https://w3id.org/np/doi",
                        }
                    ],
                }
            ]
        },
    )
    assert r.status_code == 422

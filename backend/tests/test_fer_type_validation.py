"""Coordinator follow-up: POST /api/fers validates `type` against
data/fers/fer-types.json (loaded as a cached config list, fipm.fer_types)."""

from __future__ import annotations


def test_create_fer_rejects_unknown_type(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "fertype-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "FT",
        },
    )

    bad = client.post(
        "/api/fers",
        json={
            "id": "https://example.org/fer/not-a-real-type",
            "label": {"en": "Bad"},
            "type": "not-a-real-type",
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "invalid_fer_type"

    good = client.post(
        "/api/fers",
        json={
            "id": "https://example.org/fer/good",
            "label": {"en": "Good"},
            "type": "identifier-service",
        },
    )
    assert good.status_code == 201

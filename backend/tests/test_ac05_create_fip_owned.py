"""AC5: a signed-in user can POST /api/fips without sessionId; gets an 8-char
base32 id, ownerId set, no editToken, and the FIP appears in GET /me/fips."""

from __future__ import annotations

import re

SHORT_ID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{8}$")


def test_owned_fip_creation(client):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac5-user@example.com",
            "password": "correcthorsebattery",
            "displayName": "AC5",
        },
    )
    assert r.status_code == 201
    user_id = r.json()["id"]

    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    assert created.status_code == 201
    data = created.json()

    assert SHORT_ID_RE.match(data["id"]), data["id"]
    assert data["ownerId"] == user_id
    assert "editToken" not in data

    listing = client.get("/api/me/fips")
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["items"]]
    assert data["id"] in ids

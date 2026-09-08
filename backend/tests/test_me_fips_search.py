"""Review finding 12: GET /me/fips?q previously filtered on Fip.title, which
was never set by any endpoint (always None), so ?q matched nothing. Create
and patch now set title = community.name, and the query additionally matches
the community JSON column directly so older/blank-titled rows are still
searchable."""

from __future__ import annotations


def test_search_matches_community_name_set_on_create(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "mefips-search@example.com",
            "password": "correcthorsebattery",
            "displayName": "S",
        },
    )
    created = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "community": {"name": "Utrecht Data Stewards"},
        },
    )
    assert created.status_code == 201
    assert created.json()["title"] == "Utrecht Data Stewards"

    other = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "community": {"name": "Somewhere Else"},
        },
    )
    assert other.status_code == 201

    hits = client.get("/api/me/fips", params={"q": "Utrecht"})
    assert hits.status_code == 200
    ids = [item["id"] for item in hits.json()["items"]]
    assert created.json()["id"] in ids
    assert other.json()["id"] not in ids


def test_search_matches_community_name_set_on_patch(client):
    client.post(
        "/api/auth/register",
        json={
            "email": "mefips-search-patch@example.com",
            "password": "correcthorsebattery",
            "displayName": "S",
        },
    )
    created = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    )
    fip_id = created.json()["id"]
    assert created.json()["title"] is None

    patched = client.patch(
        f"/api/fips/{fip_id}", json={"community": {"name": "Twente FAIR Community"}}
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Twente FAIR Community"

    hits = client.get("/api/me/fips", params={"q": "Twente"})
    assert fip_id in [item["id"] for item in hits.json()["items"]]

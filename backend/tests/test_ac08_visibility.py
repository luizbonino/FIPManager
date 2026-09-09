"""AC8: a private FIP returns 404 for another signed-in user and for anonymous,
200 for its owner; switching to "link" makes an anonymous GET return 200;
GET /api/knowledge-models never lists another user's private model."""

from __future__ import annotations


def test_private_fip_visibility(client, client_factory):
    owner = client
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac8-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "Owner",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    created = owner.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "private"},
    )
    fip_id = created.json()["id"]

    other = client_factory()
    other.post(
        "/api/auth/register",
        json={
            "email": "ac8-other@example.com",
            "password": "correcthorsebattery",
            "displayName": "Other",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert other.get(f"/api/fips/{fip_id}").status_code == 404

    anon = client_factory()
    assert anon.get(f"/api/fips/{fip_id}").status_code == 404

    assert owner.get(f"/api/fips/{fip_id}").status_code == 200

    link_patch = owner.patch(f"/api/fips/{fip_id}", json={"visibility": "link"})
    assert link_patch.status_code == 200

    anon2 = client_factory()
    assert anon2.get(f"/api/fips/{fip_id}").status_code == 200


def test_knowledge_models_listing_hides_other_users_private_models(
    client, client_factory, db_session
):
    from fipm.models import KnowledgeModel

    owner = client
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac8-km-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "KMOwner",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    owner_id = owner.get("/api/auth/me").json()["id"]

    private_km = KnowledgeModel(
        id="private-km",
        version="1.0.0",
        owner_id=owner_id,
        visibility="private",
        status="draft",
        license="CC0-1.0",
        source="test",
        title={"en": "Private"},
        description={"en": "Private"},
        changelog=[],
        content={"id": "private-km", "version": "1.0.0", "sections": []},
        content_sha256="x",
    )
    db_session.add(private_km)
    db_session.commit()

    other = client_factory()
    other.post(
        "/api/auth/register",
        json={
            "email": "ac8-km-other@example.com",
            "password": "correcthorsebattery",
            "displayName": "Other2",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    listing = other.get("/api/knowledge-models")
    assert listing.status_code == 200
    assert "private-km" not in [item["id"] for item in listing.json()["items"]]

    anon = client_factory()
    listing_anon = anon.get("/api/knowledge-models")
    assert "private-km" not in [item["id"] for item in listing_anon.json()["items"]]

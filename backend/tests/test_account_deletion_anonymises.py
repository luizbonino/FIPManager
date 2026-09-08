"""Review finding 2/9: DELETE /api/auth/me must not raise IntegrityError even
when the user owns workshop sessions, FERs and knowledge models (the FKs had
no ondelete). It closes+anonymises owned sessions, keeps owned FERs but clears
ownership, deletes owned draft knowledge models but anonymises published
ones, and anonymises owned FIPs while forcing their visibility to "link" so
they stay reachable by URL (an orphaned "private" FIP would otherwise be
readable by no one)."""

from __future__ import annotations

from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession


def test_delete_account_anonymises_everything_without_error(client, db_session):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe",
        },
    )
    user_id = reg.json()["id"]

    session_resp = client.post(
        "/api/sessions",
        json={
            "title": "will be closed",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    private_fip = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "private"},
    )
    assert private_fip.status_code == 201
    fip_id = private_fip.json()["id"]

    fer_resp = client.post(
        "/api/fers",
        json={
            "id": "https://example.org/fer/delme-owned",
            "label": {"en": "Owned FER"},
            "type": "identifier-service",
        },
    )
    assert fer_resp.status_code == 201

    draft_km = KnowledgeModel(
        id="delme-draft-km",
        version="1.0.0",
        owner_id=user_id,
        visibility="private",
        status="draft",
        license="CC0-1.0",
        source="test",
        title={"en": "draft"},
        description={"en": "draft"},
        changelog=[],
        content={"id": "delme-draft-km", "version": "1.0.0", "sections": []},
        content_sha256="x",
    )
    published_km = KnowledgeModel(
        id="delme-published-km",
        version="1.0.0",
        owner_id=user_id,
        visibility="public",
        status="published",
        license="CC0-1.0",
        source="test",
        title={"en": "published"},
        description={"en": "published"},
        changelog=[],
        content={"id": "delme-published-km", "version": "1.0.0", "sections": []},
        content_sha256="y",
    )
    db_session.add_all([draft_km, published_km])
    db_session.commit()

    delete = client.request(
        "DELETE", "/api/auth/me", json={"currentPassword": "correcthorsebattery"}
    )
    assert delete.status_code == 204, delete.text

    # The request was served by a different Session; drop this fixture's
    # identity-map cache so the .get() calls below re-query the DB instead of
    # returning the pre-delete objects still held in memory.
    db_session.expire_all()

    session_row = db_session.get(WorkshopSession, session_id)
    assert session_row is not None
    assert session_row.owner_id is None
    assert session_row.status == "closed"

    fip_row = db_session.get(Fip, fip_id)
    assert fip_row is not None
    assert fip_row.owner_id is None
    assert fip_row.visibility == "link"

    fer_row = db_session.get(Fer, "https://example.org/fer/delme-owned")
    assert fer_row is not None
    assert fer_row.owner_id is None

    assert db_session.get(KnowledgeModel, ("delme-draft-km", "1.0.0")) is None

    published_row = db_session.get(KnowledgeModel, ("delme-published-km", "1.0.0"))
    assert published_row is not None
    assert published_row.owner_id is None


def test_anonymised_fip_stays_readable_via_link(client, client_factory):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-readable@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe2",
        },
    )
    assert reg.status_code == 201
    created = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "private"},
    )
    fip_id = created.json()["id"]

    delete = client.request(
        "DELETE", "/api/auth/me", json={"currentPassword": "correcthorsebattery"}
    )
    assert delete.status_code == 204

    anon = client_factory()
    r = anon.get(f"/api/fips/{fip_id}")
    assert r.status_code == 200
    assert r.json()["visibility"] == "link"
    assert r.json()["ownerId"] is None

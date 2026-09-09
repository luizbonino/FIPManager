"""Review finding 2/9: DELETE /api/auth/me must not raise IntegrityError even
when the user owns workshop sessions, FERs and knowledge models (the FKs had
no ondelete). It closes+anonymises owned sessions, keeps owned FERs but clears
ownership, deletes owned draft knowledge models but anonymises published
ones.

Review finding 3: owned FIPs are handled per (visibility, session_id): a
private FIP with no session becomes unreadable by anyone once ownerless, so
it is deleted outright; a private FIP tied to a workshop session must stay
reachable by the session owner/room, so it is anonymised and downgraded to
"link" instead; non-private FIPs keep their visibility and are simply
anonymised.

AC12 (spec 04-knowledge-model-editor.md §6): owned published knowledge
models are anonymised to `owner_id IS NULL, visibility="public"` (not merely
`owner_id IS NULL`), so every FIP that references them keeps resolving and
they become read-only community content; owned drafts are deleted
outright."""

from __future__ import annotations

from fipm.models import Fer, Fip, KnowledgeModel, WorkshopSession


def test_delete_account_anonymises_everything_without_error(client, db_session):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe",
            "privacyAcceptedVersion": "test-v1",
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

    private_fip_no_session = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "private"},
    )
    assert private_fip_no_session.status_code == 201
    private_no_session_id = private_fip_no_session.json()["id"]

    link_fip = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}, "visibility": "link"},
    )
    assert link_fip.status_code == 201
    link_fip_id = link_fip.json()["id"]

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
        # AC12: starts private, must come out visibility="public" after
        # account deletion -- not merely unchanged.
        visibility="private",
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

    # A private FIP with no session becomes unreadable by anyone once
    # ownerless, so it is deleted rather than anonymised.
    assert db_session.get(Fip, private_no_session_id) is None

    # A non-private FIP is anonymised but keeps its visibility.
    link_row = db_session.get(Fip, link_fip_id)
    assert link_row is not None
    assert link_row.owner_id is None
    assert link_row.visibility == "link"

    fer_row = db_session.get(Fer, "https://example.org/fer/delme-owned")
    assert fer_row is not None
    assert fer_row.owner_id is None

    assert db_session.get(KnowledgeModel, ("delme-draft-km", "1.0.0")) is None

    published_row = db_session.get(KnowledgeModel, ("delme-published-km", "1.0.0"))
    assert published_row is not None
    assert published_row.owner_id is None
    assert published_row.visibility == "public"


def test_delete_account_ac12_published_model_referenced_by_fip_survives_readable(
    client, client_factory
):
    """AC12: a user owning one published model referenced by a FIP and one
    draft -> 204; the published row survives with owner_id IS NULL and
    visibility="public", the draft row is gone, and the FIP still exports
    (its questionnaireRef resolves)."""
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-ac12@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe4",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert reg.status_code == 201, reg.text

    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": "delme-ac12-km"})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text

    draft = client.post(
        "/api/knowledge-models", json={"title": {"en": "AC12 draft"}, "id": "delme-ac12-draft-km"}
    )
    assert draft.status_code == 201, draft.text

    fip = client.post(
        "/api/fips",
        json={"questionnaireRef": {"id": km_id, "version": "1.0.0"}, "visibility": "public"},
    )
    assert fip.status_code == 201, fip.text
    fip_id = fip.json()["id"]

    delete = client.request(
        "DELETE", "/api/auth/me", json={"currentPassword": "correcthorsebattery"}
    )
    assert delete.status_code == 204, delete.text

    anon = client_factory()
    published_row = anon.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert published_row.status_code == 200
    assert published_row.json()["ownerId"] is None
    assert published_row.json()["visibility"] == "public"

    draft_gone = anon.get("/api/knowledge-models/delme-ac12-draft-km/1.0.0")
    assert draft_gone.status_code == 404

    export = anon.get(f"/api/fips/{fip_id}/export.json")
    assert export.status_code == 200
    assert export.json()["questionnaireRef"]["id"] == km_id


def test_private_fip_without_session_is_deleted_not_readable(client, client_factory):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-deleted@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe3",
            "privacyAcceptedVersion": "test-v1",
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
    assert anon.get(f"/api/fips/{fip_id}").status_code == 404


def test_private_session_fip_stays_readable_via_link_after_deletion(client, client_factory):
    """A private FIP the user claimed inside their own session keeps its
    session_id, so on account deletion it is anonymised + downgraded to
    "link" rather than deleted, staying reachable by URL."""
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "delme-readable@example.com",
            "password": "correcthorsebattery",
            "displayName": "DelMe2",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert reg.status_code == 201
    owner_id = reg.json()["id"]

    session = client.post(
        "/api/sessions",
        json={
            "title": "delme session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "visibility": "private",
        },
    )
    assert created.status_code == 201
    fip = created.json()
    fip_id, edit_token = fip["id"], fip["editToken"]

    claim = client.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token})
    assert claim.status_code == 200
    assert claim.json()["ownerId"] == owner_id

    delete = client.request(
        "DELETE", "/api/auth/me", json={"currentPassword": "correcthorsebattery"}
    )
    assert delete.status_code == 204

    anon = client_factory()
    r = anon.get(f"/api/fips/{fip_id}")
    assert r.status_code == 200
    assert r.json()["visibility"] == "link"
    assert r.json()["ownerId"] is None

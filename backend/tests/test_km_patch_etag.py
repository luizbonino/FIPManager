"""Review finding 7 (routers/knowledge_models.py `patch_knowledge_model`):
`title`/`description` are mirrored into `content`, so a metadata PATCH that
changes either one legitimately changes `content_sha256` -- the response
must carry the new ETag so the caller can still PUT .../content afterwards
without a stale-If-Match 409. A PATCH that only changes `visibility` must
not recompute content_sha256 (no ETag header, since content didn't change)."""

from __future__ import annotations


def _register(client, email: str) -> str:
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
    return r.json()["id"]


def _make_draft(client) -> str:
    created = client.post("/api/knowledge-models", json={"title": {"en": "Original title"}})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_patch_title_returns_new_etag_matching_new_content_sha(client):
    _register(client, "patch-etag-title@example.com")
    km_id = _make_draft(client)
    etag_before = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    r = client.patch(f"/api/knowledge-models/{km_id}/1.0.0", json={"title": {"en": "New title"}})
    assert r.status_code == 200, r.text
    new_etag = r.headers.get("etag")
    assert new_etag is not None
    assert new_etag != etag_before

    # The returned ETag must be usable immediately for a PUT .../content.
    sections = r.json()["content"]["sections"]
    put = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": new_etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text

    get_after = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert get_after.json()["content"]["title"]["en"] == "New title"


def test_patch_description_also_returns_new_etag(client):
    _register(client, "patch-etag-description@example.com")
    km_id = _make_draft(client)
    etag_before = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    r = client.patch(
        f"/api/knowledge-models/{km_id}/1.0.0", json={"description": {"en": "New description"}}
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("etag") not in (None, etag_before)


def test_patch_visibility_only_has_no_etag_header_and_content_sha_unchanged(client, db_session):
    from fipm.models import KnowledgeModel

    _register(client, "patch-etag-visibility-only@example.com")
    km_id = _make_draft(client)
    sha_before = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    r = client.patch(f"/api/knowledge-models/{km_id}/1.0.0", json={"visibility": "public"})
    assert r.status_code == 200, r.text
    assert r.json()["visibility"] == "public"
    assert "etag" not in {k.lower() for k in r.headers.keys()}

    db_session.expire_all()
    row = db_session.get(KnowledgeModel, (km_id, "1.0.0"))
    assert f'"{row.content_sha256}"' == sha_before

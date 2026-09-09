"""Review finding 13 (routers/knowledge_models.py `publish_knowledge_model`):
`If-Match` is optional on publish (unlike PUT .../content, where it's
required), but when present and stale it must still be honoured -- 409
`content_conflict` with the current etag, so a facilitator who loaded the
draft, then someone else edited it, doesn't publish over that edit blind."""

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


def test_publish_with_stale_if_match_is_409_content_conflict(client):
    _register(client, "publish-conflict-stale@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    stale_etag = get1.headers["etag"]
    sections = get1.json()["content"]["sections"]
    sections[0]["questions"][0]["text"]["en"] = "Edited before publish"

    put = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": stale_etag},
        json={"sections": sections},
    )
    assert put.status_code == 200, put.text
    current_etag = put.headers["etag"]
    assert current_etag != stale_etag

    r = client.post(
        f"/api/knowledge-models/{km_id}/1.0.0/publish",
        headers={"If-Match": stale_etag},
        json={"notes": "release"},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == "content_conflict"
    assert body["etag"] == current_etag

    # The draft must not have been published by the rejected call.
    still_draft = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert still_draft.json()["status"] == "draft"


def test_publish_with_current_if_match_succeeds(client):
    _register(client, "publish-conflict-current@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    current_etag = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    r = client.post(
        f"/api/knowledge-models/{km_id}/1.0.0/publish",
        headers={"If-Match": current_etag},
        json={"notes": "release"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"


def test_publish_without_if_match_still_works(client):
    _register(client, "publish-conflict-absent@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "release"})
    assert r.status_code == 200, r.text

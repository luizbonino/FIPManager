"""AC2 (spec 04 §6): fork -> edit content via PUT with If-Match (new ETag) ->
publish (422 no body, 400 empty notes, 200 with real notes, changelog entry
appended) -> content is frozen (409 model_published) but visibility keeps
working via PATCH."""

from __future__ import annotations

from datetime import UTC, datetime


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


def test_edit_and_publish_cycle(client):
    _register(client, "publish-cycle@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert get1.status_code == 200
    etag1 = get1.headers["etag"]

    sections = get1.json()["content"]["sections"]
    sections[0]["questions"][0]["text"]["en"] = "Edited question text"

    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections},
    )
    assert put1.status_code == 200, put1.text
    etag2 = put1.headers["etag"]
    assert etag2 != etag1
    assert put1.json()["content"]["sections"][0]["questions"][0]["text"]["en"] == (
        "Edited question text"
    )

    no_body = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={})
    assert no_body.status_code == 422

    empty_notes = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": ""})
    assert empty_notes.status_code == 400
    assert empty_notes.json()["detail"] == "changelog_notes_required"

    published = client.post(
        f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "First release"}
    )
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["status"] == "published"
    today = datetime.now(UTC).date().isoformat()
    assert body["changelog"][-1] == {"version": "1.0.0", "date": today, "notes": "First release"}

    put_after_publish = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag2},
        json={"sections": sections},
    )
    assert put_after_publish.status_code == 409
    assert put_after_publish.json()["detail"] == "model_published"

    patch_visibility = client.patch(
        f"/api/knowledge-models/{km_id}/1.0.0", json={"visibility": "public"}
    )
    assert patch_visibility.status_code == 200, patch_visibility.text
    assert patch_visibility.json()["visibility"] == "public"

    patch_title_on_published = client.patch(
        f"/api/knowledge-models/{km_id}/1.0.0", json={"title": {"en": "Nope"}}
    )
    assert patch_title_on_published.status_code == 409
    assert patch_title_on_published.json()["detail"] == "model_published"

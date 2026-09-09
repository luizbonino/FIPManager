"""AC8 (spec 04 §6): a second signed-in user gets 404 `not_found` from every
write route and from GET on the first user's private draft; an anonymous
client gets 401 on the five write routes."""

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


def _make_private_draft(client, km_id: str) -> str:
    created = client.post(
        "/api/knowledge-models", json={"title": {"en": "Private Draft"}, "id": km_id}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_non_owner_gets_404_everywhere(client, client_factory):
    _register(client, "owner-nonowner@example.com")
    km_id = _make_private_draft(client, "private-draft-nonowner-km")

    etag = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    other = client_factory()
    _register(other, "other-nonowner@example.com")

    assert other.get(f"/api/knowledge-models/{km_id}/1.0.0").status_code == 404

    put = other.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag},
        json={"sections": []},
    )
    assert put.status_code == 404

    patch = other.patch(f"/api/knowledge-models/{km_id}/1.0.0", json={"visibility": "public"})
    assert patch.status_code == 404

    publish = other.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "x"})
    assert publish.status_code == 404

    # new-version requires a published row; still must 404 before that check
    # for a non-owner (existence must not leak either way).
    new_version = other.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert new_version.status_code == 404

    delete = other.request("DELETE", f"/api/knowledge-models/{km_id}/1.0.0")
    assert delete.status_code == 404


def test_anonymous_gets_401_on_write_routes(client, raw_client):
    _register(client, "owner-anon@example.com")
    km_id = _make_private_draft(client, "private-draft-anon-km")
    etag = client.get(f"/api/knowledge-models/{km_id}/1.0.0").headers["etag"]

    assert (
        raw_client.put(
            f"/api/knowledge-models/{km_id}/1.0.0/content",
            headers={"If-Match": etag, "origin": "http://testserver"},
            json={"sections": []},
        ).status_code
        == 401
    )
    assert (
        raw_client.patch(
            f"/api/knowledge-models/{km_id}/1.0.0",
            headers={"origin": "http://testserver"},
            json={"visibility": "public"},
        ).status_code
        == 401
    )
    assert (
        raw_client.post(
            f"/api/knowledge-models/{km_id}/1.0.0/publish",
            headers={"origin": "http://testserver"},
            json={"notes": "x"},
        ).status_code
        == 401
    )
    assert (
        raw_client.post(
            f"/api/knowledge-models/{km_id}/1.0.0/new-version",
            headers={"origin": "http://testserver"},
            json={},
        ).status_code
        == 401
    )
    assert (
        raw_client.request(
            "DELETE",
            f"/api/knowledge-models/{km_id}/1.0.0",
            headers={"origin": "http://testserver"},
        ).status_code
        == 401
    )

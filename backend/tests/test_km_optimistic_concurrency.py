"""AC9 (spec 04 §6): two PUT .../content calls with the same If-Match -- the
first 200, the second 409 `content_conflict` with the current etag in the
body, and the draft holds the first write; PUT with no If-Match is 428
`if_match_required`; `If-Match: "*"` is not treated as a wildcard."""

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


def _fork_test_km(client) -> str:
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    assert fork.status_code == 201, fork.text
    return fork.json()["id"]


def test_two_puts_with_same_if_match_second_conflicts(client):
    _register(client, "concurrency-basic@example.com")
    km_id = _fork_test_km(client)
    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    sections = get1.json()["content"]["sections"]

    sections_a = [dict(s) for s in sections]
    sections_a[0] = dict(sections_a[0])
    sections_a[0]["questions"] = list(sections_a[0]["questions"])
    sections_a[0]["questions"][0] = dict(sections_a[0]["questions"][0])
    sections_a[0]["questions"][0]["text"] = {"en": "First writer's text"}

    first = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections_a},
    )
    assert first.status_code == 200, first.text
    etag2 = first.headers["etag"]
    assert etag2 != etag1

    sections_b = [dict(s) for s in sections]
    sections_b[0] = dict(sections_b[0])
    sections_b[0]["questions"] = list(sections_b[0]["questions"])
    sections_b[0]["questions"][0] = dict(sections_b[0]["questions"][0])
    sections_b[0]["questions"][0]["text"] = {"en": "Second writer's text (stale)"}

    second = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections_b},
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["detail"] == "content_conflict"
    assert body["etag"] == etag2

    current = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert current.headers["etag"] == etag2
    assert (
        current.json()["content"]["sections"][0]["questions"][0]["text"]["en"]
        == "First writer's text"
    )


def test_put_without_if_match_is_428(client):
    _register(client, "concurrency-428@example.com")
    km_id = _fork_test_km(client)
    sections = client.get(f"/api/knowledge-models/{km_id}/1.0.0").json()["content"]["sections"]

    r = client.put(f"/api/knowledge-models/{km_id}/1.0.0/content", json={"sections": sections})
    assert r.status_code == 428
    assert r.json()["detail"] == "if_match_required"


def test_wildcard_if_match_is_not_accepted(client):
    _register(client, "concurrency-wildcard@example.com")
    km_id = _fork_test_km(client)
    sections = client.get(f"/api/knowledge-models/{km_id}/1.0.0").json()["content"]["sections"]

    r = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": "*"},
        json={"sections": sections},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "content_conflict"

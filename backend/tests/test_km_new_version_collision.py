"""Review findings 1 & 9 (routers/knowledge_models.py `new_knowledge_model_version`,
`list_versions`, `_parse_semver`): an explicit `version` that collides with an
existing (id, version) row is 409 `version_exists` instead of an unhandled
IntegrityError; the default bump is computed from the *highest* existing
version for this model id, not from the row being new-versioned, so it can't
collide with a published version that already sits above it; `_parse_semver`
rejects non-canonical parts (leading zeros); `GET .../versions` is ordered
newest-first."""

from __future__ import annotations


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _fork_and_publish(client, *, new_id: str) -> str:
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": new_id})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text
    return km_id


def test_explicit_version_colliding_with_existing_row_is_409(client):
    _register(client, "newver-collide-explicit@example.com")
    km_id = _fork_and_publish(client, new_id="newver-collide-explicit-km")

    # Create and publish 1.1.0 so the model now has two published rows.
    bump = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert bump.status_code == 201, bump.text
    assert bump.json()["version"] == "1.1.0"
    publish_bump = client.post(
        f"/api/knowledge-models/{km_id}/1.1.0/publish", json={"notes": "second release"}
    )
    assert publish_bump.status_code == 200, publish_bump.text

    # new-version on 1.0.0 explicitly asking for "1.1.0" (> 1.0.0, so it
    # passes the version_not_greater check) collides with the row just
    # published above.
    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={"version": "1.1.0"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "version_exists"


def test_default_bump_uses_highest_existing_version_not_the_source_row(client):
    _register(client, "newver-highest-bump@example.com")
    km_id = _fork_and_publish(client, new_id="newver-highest-bump-km")

    bump = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert bump.status_code == 201, bump.text
    assert bump.json()["version"] == "1.1.0"
    publish_bump = client.post(
        f"/api/knowledge-models/{km_id}/1.1.0/publish", json={"notes": "second release"}
    )
    assert publish_bump.status_code == 200, publish_bump.text

    # Calling new-version again on the *older* published row (1.0.0) with no
    # explicit version must not try to recreate "1.1.0" (which already
    # exists) -- it must bump from the highest existing version (1.1.0).
    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == "1.2.0"


def test_list_versions_ordered_newest_first(client):
    _register(client, "newver-list-order@example.com")
    km_id = _fork_and_publish(client, new_id="newver-list-order-km")
    bump = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert bump.status_code == 201, bump.text
    publish_bump = client.post(
        f"/api/knowledge-models/{km_id}/1.1.0/publish", json={"notes": "second release"}
    )
    assert publish_bump.status_code == 200, publish_bump.text

    r = client.get(f"/api/knowledge-models/{km_id}/versions")
    assert r.status_code == 200, r.text
    versions = [item["version"] for item in r.json()["items"]]
    assert versions == ["1.1.0", "1.0.0"]


def test_explicit_leading_zero_version_is_400_invalid_version(client):
    _register(client, "newver-leading-zero@example.com")
    km_id = _fork_and_publish(client, new_id="newver-leading-zero-km")

    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={"version": "01.0.0"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "invalid_version"

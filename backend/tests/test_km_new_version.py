"""AC10 (spec 04 §6): POST .../new-version on a published row -- default
bump minor (1.0.0 -> 1.1.0), bump=patch (1.0.1), bump=major (2.0.0), an
explicit version that is not strictly greater is 400 `version_not_greater`,
a second call while a draft exists is 409 `draft_exists`, and calling it on
a draft is 409 `not_published`."""

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


def _fork_and_publish(client, *, new_id: str) -> str:
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": new_id})
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text
    return km_id


def test_default_bump_is_minor(client):
    _register(client, "newver-minor@example.com")
    km_id = _fork_and_publish(client, new_id="newver-minor-km")
    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == "1.1.0"
    assert body["status"] == "draft"


def test_bump_patch_and_major(client):
    _register(client, "newver-patch-major@example.com")
    km_patch = _fork_and_publish(client, new_id="newver-patch-km")
    r_patch = client.post(
        f"/api/knowledge-models/{km_patch}/1.0.0/new-version", json={"bump": "patch"}
    )
    assert r_patch.status_code == 201, r_patch.text
    assert r_patch.json()["version"] == "1.0.1"

    km_major = _fork_and_publish(client, new_id="newver-major-km")
    r_major = client.post(
        f"/api/knowledge-models/{km_major}/1.0.0/new-version", json={"bump": "major"}
    )
    assert r_major.status_code == 201, r_major.text
    assert r_major.json()["version"] == "2.0.0"


def test_explicit_version_not_greater_is_400(client):
    _register(client, "newver-not-greater@example.com")
    km_id = _fork_and_publish(client, new_id="newver-not-greater-km")
    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={"version": "0.9.0"})
    assert r.status_code == 400
    assert r.json()["detail"] == "version_not_greater"


def test_second_new_version_while_draft_exists_conflicts(client):
    _register(client, "newver-draft-exists@example.com")
    km_id = _fork_and_publish(client, new_id="newver-draft-exists-km")
    first = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert first.status_code == 201, first.text

    second = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert second.status_code == 409
    assert second.json()["detail"] == "draft_exists"


def test_new_version_on_a_draft_is_not_published(client):
    _register(client, "newver-on-draft@example.com")
    fork = client.post(
        "/api/knowledge-models/test-km/1.0.0/fork", json={"newId": "newver-on-draft-km"}
    )
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]

    r = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "not_published"

"""AC7 (spec 04 §6): deleting a published version referenced by a FIP is
409 `model_in_use` and the row survives; deleting a draft is 204 and it's
gone; deleting a system model as a non-admin is 403
`system_model_readonly`."""

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


def test_delete_published_in_use_conflicts_and_survives(client):
    _register(client, "delete-in-use@example.com")
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={})
    km_id = fork.json()["id"]
    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text

    fip = client.post("/api/fips", json={"questionnaireRef": {"id": km_id, "version": "1.0.0"}})
    assert fip.status_code == 201, fip.text

    delete = client.request("DELETE", f"/api/knowledge-models/{km_id}/1.0.0")
    assert delete.status_code == 409
    assert delete.json()["detail"] == "model_in_use"

    still_there = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    assert still_there.status_code == 200


def test_delete_draft_succeeds_and_disappears(client):
    _register(client, "delete-draft@example.com")
    created = client.post(
        "/api/knowledge-models", json={"title": {"en": "Delete me"}, "id": "delete-draft-km"}
    )
    assert created.status_code == 201, created.text

    delete = client.request("DELETE", "/api/knowledge-models/delete-draft-km/1.0.0")
    assert delete.status_code == 204

    gone = client.get("/api/knowledge-models/delete-draft-km/1.0.0")
    assert gone.status_code == 404


def test_delete_system_model_forbidden_for_non_admin(client):
    _register(client, "delete-system@example.com")
    delete = client.request("DELETE", "/api/knowledge-models/test-km/1.0.0")
    assert delete.status_code == 403
    assert delete.json()["detail"] == "system_model_readonly"

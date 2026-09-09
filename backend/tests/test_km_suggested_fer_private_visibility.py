"""Review finding 5: the router's known-FER-ids snapshot
(`routers.knowledge_models._known_fer_snapshot`) must apply the same
visibility rule as `routers.fers.list_fers` (seed, user-promoted, model, or
the caller's own FERs) -- a question's `suggestedFerIds` must not resolve
against another user's still-private `source="user"` FER, which no one else
(including that other user's own future readers of this model) can actually
see via `GET /api/fers`."""

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


_SECTIONS = [
    {
        "id": "sec1",
        "title": {"en": "Section 1"},
        "questions": [{"id": "q1", "text": {"en": "Question 1"}, "ferType": "identifier-service"}],
    }
]


def test_another_users_private_fer_is_rejected_as_unknown_suggested_fer(client_factory):
    owner = client_factory()
    _register(owner, "ac-fer-vis-owner@example.com")
    private_fer = owner.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/private-one",
            "label": {"en": "Owner's private registry"},
            "type": "identifier-service",
        },
    )
    assert private_fer.status_code == 201, private_fer.text
    fer_id = private_fer.json()["id"]

    other = client_factory()
    _register(other, "ac-fer-vis-other@example.com")
    created = other.post("/api/knowledge-models", json={"title": {"en": "Other's model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    get1 = other.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    sections = [dict(_SECTIONS[0])]
    sections[0] = {**sections[0], "questions": [dict(sections[0]["questions"][0])]}
    sections[0]["questions"][0]["suggestedFerIds"] = [fer_id]

    put1 = other.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections},
    )
    assert put1.status_code == 400, put1.text
    assert put1.json()["detail"] == "invalid_content"
    codes = {e["code"] for e in put1.json()["errors"]}
    assert "unknown_suggested_fer" in codes


def test_a_users_own_private_fer_resolves_in_their_own_model(client_factory):
    owner = client_factory()
    _register(owner, "ac-fer-vis-self@example.com")
    private_fer = owner.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/own-private-one",
            "label": {"en": "My own private registry"},
            "type": "identifier-service",
        },
    )
    assert private_fer.status_code == 201, private_fer.text
    fer_id = private_fer.json()["id"]

    created = owner.post("/api/knowledge-models", json={"title": {"en": "My model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    get1 = owner.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    sections = [dict(_SECTIONS[0])]
    sections[0] = {**sections[0], "questions": [dict(sections[0]["questions"][0])]}
    sections[0]["questions"][0]["suggestedFerIds"] = [fer_id]

    put1 = owner.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections},
    )
    assert put1.status_code == 200, put1.text

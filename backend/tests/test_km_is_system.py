"""Review finding 12 (models.KnowledgeModel.is_system, schemas.km_summary_dict):
`isSystem` in the `GET /knowledge-models` summary must be true only for rows
the importer loaded from data/knowledge-models/*.json -- not merely
`ownerId IS NULL`, which is also what an account-deletion-anonymised
published model ends up with (spec 04 §1), and that's community content, not
a built-in system model."""

from __future__ import annotations

from fipm.models import KnowledgeModel


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


def test_importer_seeded_model_is_system_true(db_session):
    row = db_session.get(KnowledgeModel, ("test-km", "1.0.0"))
    assert row is not None
    assert row.is_system is True


def test_user_created_draft_is_system_false(client, db_session):
    _register(client, "is-system-user-draft@example.com")
    created = client.post(
        "/api/knowledge-models",
        json={"title": {"en": "Not a system model"}, "id": "is-system-user-draft-km"},
    )
    assert created.status_code == 201, created.text

    row = db_session.get(KnowledgeModel, ("is-system-user-draft-km", "1.0.0"))
    assert row.is_system is False

    listing = client.get("/api/knowledge-models", params={"mine": "true"})
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["items"] if i["id"] == "is-system-user-draft-km")
    assert item["isSystem"] is False


def test_summary_reports_is_system_true_for_a_real_system_model(client):
    listing = client.get("/api/knowledge-models")
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["items"] if i["id"] == "test-km")
    assert item["isSystem"] is True
    assert item["ownerId"] is None


def test_anonymised_published_model_stays_is_system_false_after_account_deletion(
    client, client_factory
):
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "is-system-anon-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "AnonMe",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert reg.status_code == 201, reg.text

    fork = client.post(
        "/api/knowledge-models/test-km/1.0.0/fork", json={"newId": "is-system-anon-km"}
    )
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    published = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert published.status_code == 200, published.text

    delete = client.request(
        "DELETE", "/api/auth/me", json={"currentPassword": "correcthorsebattery"}
    )
    assert delete.status_code == 204, delete.text

    anon = client_factory()
    listing = anon.get("/api/knowledge-models")
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()["items"] if i["id"] == km_id)
    assert item["ownerId"] is None
    assert item["isSystem"] is False

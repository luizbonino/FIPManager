"""AC4 (spec 05-v1-completion.md §8): POST /api/admin/fers/{id}/promote sets
ownerId=null and source="user-promoted" and makes the FER visible to an
anonymous GET /api/fers; a second promote returns 409 not_promotable.
.../merge re-points every ferId and successorFerId equal to the source
across all FIPs, deletes the source row, reports the counts, and rejects a
source="user" target with 409 invalid_merge_target."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import User

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _promote_to_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()


def test_promote_makes_fer_globally_visible_and_is_idempotent_guarded(client_factory):
    admin = client_factory()
    _register(admin, "ac05-4-admin@example.com")
    _promote_to_admin("ac05-4-admin@example.com")

    contributor = client_factory()
    _register(contributor, "ac05-4-contributor@example.com")
    created = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-contrib",
            "label": {"en": "Contributor Registry"},
            "type": "metadata-schema",
        },
    )
    assert created.status_code == 201
    fer_id = created.json()["id"]

    anon_before = client_factory().get("/api/fers")
    assert not any(f["id"] == fer_id for f in anon_before.json()["items"])

    promoted = admin.post(f"/api/admin/fers/{fer_id}/promote")
    assert promoted.status_code == 200
    body = promoted.json()
    assert body["source"] == "user-promoted"

    anon_after = client_factory().get("/api/fers")
    assert any(f["id"] == fer_id for f in anon_after.json()["items"])

    second_promote = admin.post(f"/api/admin/fers/{fer_id}/promote")
    assert second_promote.status_code == 409
    assert second_promote.json()["detail"] == "not_promotable"


def test_merge_repoints_fer_and_successor_and_deletes_source(client_factory):
    admin = client_factory()
    _register(admin, "ac05-4-merge-admin@example.com")
    _promote_to_admin("ac05-4-merge-admin@example.com")

    contributor = client_factory()
    _register(contributor, "ac05-4-merge-contrib@example.com")
    source = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-source",
            "label": {"en": "Old Registry"},
            "type": "metadata-schema",
        },
    ).json()
    target = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-target",
            "label": {"en": "New Registry"},
            "type": "metadata-schema",
        },
    ).json()
    admin.post(f"/api/admin/fers/{target['id']}/promote")

    fip = contributor.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [
                        {"ferId": source["id"], "status": "current"},
                        {
                            "ferId": source["id"],
                            "status": "planned-replacement",
                            "successorFerId": source["id"],
                        },
                    ],
                }
            ],
        },
    ).json()

    merged = admin.post(f"/api/admin/fers/{source['id']}/merge", json={"targetFerId": target["id"]})
    assert merged.status_code == 200
    body = merged.json()
    assert body["repointedDeclarations"] == 3  # ferId x2 + successorFerId x1
    assert body["repointedFips"] == 1

    after = contributor.get(f"/api/fips/{fip['id']}").json()
    for answer in after["answers"]:
        for decl in answer["declarations"]:
            assert decl.get("ferId") != source["id"]
            assert decl.get("successorFerId") != source["id"]

    gone = client_factory().get("/api/fers", params={"q": "old registry"})
    assert not any(f["id"] == source["id"] for f in gone.json()["items"])


def test_merge_same_fer_and_invalid_target(client_factory):
    admin = client_factory()
    _register(admin, "ac05-4-invalid-admin@example.com")
    _promote_to_admin("ac05-4-invalid-admin@example.com")

    contributor = client_factory()
    _register(contributor, "ac05-4-invalid-contrib@example.com")
    a = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-a",
            "label": {"en": "A"},
            "type": "metadata-schema",
        },
    ).json()
    b = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-b",
            "label": {"en": "B"},
            "type": "metadata-schema",
        },
    ).json()

    same = admin.post(f"/api/admin/fers/{a['id']}/merge", json={"targetFerId": a["id"]})
    assert same.status_code == 400
    assert same.json()["detail"] == "same_fer"

    # b is still source="user" (never promoted) -> invalid merge target.
    invalid = admin.post(f"/api/admin/fers/{a['id']}/merge", json={"targetFerId": b["id"]})
    assert invalid.status_code == 409
    assert invalid.json()["detail"] == "invalid_merge_target"

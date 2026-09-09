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
                        {"ferId": source["id"], "status": "none"},
                        # A successorFerId equal to *this declaration's own*
                        # ferId is rejected as successor_same_as_fer (review
                        # finding 8), so this one's ferId is unrelated --
                        # only its successorFerId points at the source FER
                        # being merged away.
                        {
                            "ferId": "https://example.org/fers/ac05-4-unrelated",
                            "status": "planned-replacement",
                            "successorFerId": source["id"],
                        },
                    ],
                }
            ],
        },
    )
    assert fip.status_code == 201, fip.text
    fip = fip.json()

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


def test_merge_rejects_seed_source_and_mismatched_type(client_factory):
    """Review finding 4: a source="seed" FER (loaded by the importer, e.g.
    data/fers/seed.json's DOI entry) can't be merged away -- there's no
    other delete route for FERs, so this is the only place that needs
    guarding. And a merge target of a different `type` than the source is
    rejected too, since repointing would silently change what every
    declaration asserts."""
    admin = client_factory()
    _register(admin, "ac05-4-seed-admin@example.com")
    _promote_to_admin("ac05-4-seed-admin@example.com")

    contributor = client_factory()
    _register(contributor, "ac05-4-seed-contrib@example.com")
    same_type_target = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-seed-target",
            "label": {"en": "Identifier service target"},
            "type": "identifier-service",
        },
    ).json()
    admin.post(f"/api/admin/fers/{same_type_target['id']}/promote")

    seed_fer_id = "https://w3id.org/np/doi"  # type identifier-service, source="seed"
    protected = admin.post(
        f"/api/admin/fers/{seed_fer_id}/merge", json={"targetFerId": same_type_target["id"]}
    )
    assert protected.status_code == 409
    assert protected.json()["detail"] == "seed_fer_protected"

    source = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-mismatch-source",
            "label": {"en": "Mismatch source"},
            "type": "identifier-service",
        },
    ).json()
    different_type_target = contributor.post(
        "/api/fers",
        json={
            "id": "https://example.org/fers/ac05-4-mismatch-target",
            "label": {"en": "Mismatch target"},
            "type": "metadata-schema",
        },
    ).json()
    admin.post(f"/api/admin/fers/{different_type_target['id']}/promote")

    mismatched = admin.post(
        f"/api/admin/fers/{source['id']}/merge",
        json={"targetFerId": different_type_target["id"]},
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["detail"] == "invalid_merge_target"


def test_admin_fers_limit_and_offset_are_clamped(client_factory):
    """Review finding 12: same limit=1..200/offset>=0 clamp as
    GET /api/admin/users."""
    admin = client_factory()
    _register(admin, "ac05-4-clamp-admin@example.com")
    _promote_to_admin("ac05-4-clamp-admin@example.com")

    too_big_limit = admin.get("/api/admin/fers", params={"limit": 500})
    assert too_big_limit.status_code == 422

    negative_offset = admin.get("/api/admin/fers", params={"offset": -5})
    assert negative_offset.status_code == 422

    ok = admin.get("/api/admin/fers", params={"limit": 1, "offset": 0})
    assert ok.status_code == 200

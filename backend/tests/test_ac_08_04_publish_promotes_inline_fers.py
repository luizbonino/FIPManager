"""spec 08-workshop-picklists.md §6 AC4: publishing a model with two
`inlineFers` creates two `fers` rows with `source="model"` and `owner_id` =
the model owner, reports `{created: 2, skipped: 0}`, and a second publish
reports `{created: 0, skipped: 2}` without touching the rows; a seed row
with the same id is never overwritten. Review finding 4: promotion only
happens for a public/link model -- a private one keeps its `inlineFers`
inline. Review finding 1: after promotion, the published content's
`inlineFers` is rewritten so the very next new-version / PUT .../content /
publish / fork on this model doesn't re-flag the promoted entries as
`inline_fer_duplicates_catalogue`."""

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


_SECTIONS_WITH_QUESTION = [
    {
        "id": "sec1",
        "title": {"en": "Section 1"},
        "questions": [{"id": "q1", "text": {"en": "Question 1"}, "ferType": "identifier-service"}],
    }
]


def _publish_with_inline_fers(
    client, km_id: str, inline_fers: list[dict], *, visibility: str = "public"
) -> dict:
    # Review finding 4: promotion only happens for a public/link model.
    vis = client.patch(f"/api/knowledge-models/{km_id}/1.0.0", json={"visibility": visibility})
    assert vis.status_code == 200, vis.text
    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": _SECTIONS_WITH_QUESTION, "inlineFers": inline_fers},
    )
    assert put1.status_code == 200, put1.text
    pub1 = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "go"})
    assert pub1.status_code == 200, pub1.text
    return pub1.json()


def test_publish_promotes_two_inline_fers_and_is_idempotent(client):
    user_id = _register(client, "ac08-04@example.com")
    created = client.post("/api/knowledge-models", json={"title": {"en": "Inline FER model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    inline_fers = [
        {
            "id": "https://fipm.example.org/fers/draft/aaaaaaaaaaaaaaaa",
            "label": {"pt-BR": "Vocabulário A"},
            "type": "structured-vocabulary",
            "homepage": None,
        },
        {
            "id": "https://fipm.example.org/fers/draft/bbbbbbbbbbbbbbbb",
            "label": {"pt-BR": "Vocabulário B"},
            "type": "structured-vocabulary",
            "homepage": None,
        },
    ]

    body1 = _publish_with_inline_fers(client, km_id, inline_fers)
    assert body1["promotedFers"] == {"created": 2, "skipped": 0}

    for entry in inline_fers:
        fer_list = client.get("/api/fers", params={"source": "model", "q": "vocabulário"})
        assert fer_list.status_code == 200
        ids = {item["id"] for item in fer_list.json()["items"]}
        assert entry["id"] in ids

    admin_fers = client.get(
        "/api/fers", params={"source": "model", "q": "vocabulário", "limit": 50}
    ).json()["items"]
    by_id = {item["id"]: item for item in admin_fers}
    assert by_id[inline_fers[0]["id"]]["source"] == "model"

    # spec §1.3: owner_id = the model's owner. Not on FerOut, so check via
    # the admin FER list (owner_email), same as an admin curating the
    # catalogue would.
    from fipm.db import SessionLocal
    from fipm.models import Fer, User

    with SessionLocal() as db:
        row = db.get(Fer, inline_fers[0]["id"])
        assert row is not None
        assert row.source == "model"
        assert row.owner_id == user_id
        owner = db.get(User, user_id)
        assert owner is not None

    # A model can't literally re-declare an id that's now in the catalogue
    # as its own `inlineFers` (rule 12 `inline_fer_duplicates_catalogue`
    # would then refuse to publish it -- correctly: it's no longer "staged",
    # it's a real catalogue FER now, referenced via `suggestedFerIds`
    # instead). §1.3's "a second publish reports {created: 0, skipped: 2}
    # without touching the rows" is the promotion *mechanism*'s own
    # idempotency -- exercised directly here, the same call
    # `publish_knowledge_model` makes.
    from fipm.importer import promote_inline_fers

    with SessionLocal() as db:
        content = {"inlineFers": inline_fers}
        result = promote_inline_fers(db, content, owner_id=user_id)
        assert result == {"created": 0, "skipped": 2}
        row = db.get(Fer, inline_fers[0]["id"])
        assert row.label == {"pt-BR": "Vocabulário A"}  # untouched, not overwritten


def test_publish_clears_inline_fers_and_new_version_put_publish_and_fork_all_succeed(client):
    """Review finding 1 (CRITICAL): before this fix, publishing a model with
    `inlineFers` promoted them into `fers` but left the published content's
    `inlineFers` unchanged, so the very next `validate_content` call (a
    new-version's copied content, a PUT .../content, a second publish, or a
    fork) saw those same ids in the catalogue and rejected the content as
    `inline_fer_duplicates_catalogue` -- 400 on every one of those four
    operations. This exercises the full chain end to end."""
    _register(client, "ac08-04c@example.com")
    created = client.post("/api/knowledge-models", json={"title": {"en": "Chain model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]

    inline_fers = [
        {
            "id": "https://fipm.example.org/fers/draft/eeeeeeeeeeeeeeee",
            "label": {"en": "Chain vocabulary"},
            "type": "structured-vocabulary",
            "homepage": None,
        }
    ]
    body1 = _publish_with_inline_fers(client, km_id, inline_fers)
    assert body1["promotedFers"] == {"created": 1, "skipped": 0}
    # The published row's own content no longer carries the now-catalogued
    # entry.
    assert body1["content"]["inlineFers"] == []

    # new-version: copies the (now-cleared) published content into a fresh
    # draft -- must succeed, not 409/400.
    new_version = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert new_version.status_code == 201, new_version.text
    draft = new_version.json()
    assert draft["version"] == "1.1.0"

    # PUT .../content on the new draft, resubmitting the *same* inlineFers
    # entry (e.g. a client that hasn't refreshed since the last publish) --
    # the known_fer_sources bypass (source="model", same id) must let this
    # through instead of 400ing.
    get_draft = client.get(f"/api/knowledge-models/{km_id}/1.1.0")
    etag_draft = get_draft.headers["etag"]
    put_draft = client.put(
        f"/api/knowledge-models/{km_id}/1.1.0/content",
        headers={"If-Match": etag_draft},
        json={"sections": _SECTIONS_WITH_QUESTION, "inlineFers": inline_fers},
    )
    assert put_draft.status_code == 200, put_draft.text

    # Publishing again must also succeed, and skip (not re-create) the
    # already-promoted row.
    pub2 = client.post(f"/api/knowledge-models/{km_id}/1.1.0/publish", json={"notes": "again"})
    assert pub2.status_code == 200, pub2.text
    assert pub2.json()["promotedFers"] == {"created": 0, "skipped": 1}

    # Forking the published model must also succeed.
    fork = client.post(f"/api/knowledge-models/{km_id}/1.1.0/fork", json={})
    assert fork.status_code == 201, fork.text


def test_private_model_inline_fers_are_never_promoted(client):
    """Review finding 4: a private model's inlineFers stay inline at
    publish -- they must never become globally-visible `source="model"`
    catalogue rows an anonymous or unrelated caller could see."""
    _register(client, "ac08-04d@example.com")
    created = client.post("/api/knowledge-models", json={"title": {"en": "Private model"}})
    assert created.status_code == 201, created.text
    km_id = created.json()["id"]
    assert created.json()["visibility"] == "private"

    inline_fers = [
        {
            "id": "https://fipm.example.org/fers/draft/ffffffffffffffff",
            "label": {"en": "Private vocabulary"},
            "type": "structured-vocabulary",
            "homepage": None,
        }
    ]
    body = _publish_with_inline_fers(client, km_id, inline_fers, visibility="private")
    assert body["promotedFers"] == {"created": 0, "skipped": 0}
    # The entry stays inline -- not promoted, not stripped out.
    assert body["content"]["inlineFers"] == inline_fers

    from fipm.db import SessionLocal
    from fipm.models import Fer

    with SessionLocal() as db:
        assert db.get(Fer, inline_fers[0]["id"]) is None

    anon = client.get("/api/fers", params={"source": "model", "q": "private vocabulary"})
    assert anon.status_code == 200
    assert anon.json()["items"] == []


def test_publish_never_overwrites_a_seed_row_with_the_same_id(client):
    """A model that (implausibly, but per spec) declares an `inlineFers`
    entry sharing an id with an existing seed FER must not overwrite it --
    but `validate_content` rule 12 (`inline_fer_duplicates_catalogue`)
    already refuses to publish such a model in the first place, so this
    confirms the 400 rather than a silent overwrite."""
    _register(client, "ac08-04b@example.com")
    created = client.post("/api/knowledge-models", json={"title": {"en": "Seed clash model"}})
    km_id = created.json()["id"]
    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    sections = get1.json()["content"]["sections"]
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={
            "sections": sections,
            "inlineFers": [
                {
                    "id": "https://w3id.org/np/doi",  # a real seed FER id
                    "label": {"en": "Not actually DOI"},
                    "type": "identifier-service",
                }
            ],
        },
    )
    assert put1.status_code == 400, put1.text
    assert put1.json()["detail"] == "invalid_content"
    codes = {e["code"] for e in put1.json()["errors"]}
    assert "inline_fer_duplicates_catalogue" in codes

    from fipm.db import SessionLocal
    from fipm.models import Fer

    with SessionLocal() as db:
        row = db.get(Fer, "https://w3id.org/np/doi")
        assert row is not None
        assert row.source == "seed"
        assert row.label.get("en") == "DOI"

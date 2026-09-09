"""spec 08-workshop-picklists.md §6 AC4: publishing a model with two
`inlineFers` creates two `fers` rows with `source="model"` and `owner_id` =
the model owner, reports `{created: 2, skipped: 0}`, and a second publish
reports `{created: 0, skipped: 2}` without touching the rows; a seed row
with the same id is never overwritten."""

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


def _publish_with_inline_fers(client, km_id: str, inline_fers: list[dict]) -> dict:
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

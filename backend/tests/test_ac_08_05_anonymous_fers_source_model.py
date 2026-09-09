"""spec 08-workshop-picklists.md §6 AC5: `GET /api/fers` as an anonymous
caller returns `source="model"` rows -- a workshop participant has no
account and must still see the options their model suggests."""

from __future__ import annotations


def test_anonymous_caller_sees_model_source_fers(client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac08-05@example.com",
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    from fipm.db import SessionLocal
    from fipm.models import Fer

    fer_id = "https://fipm.example.org/fers/draft/cccccccccccccccc"
    with SessionLocal() as db:
        db.add(
            Fer(
                id=fer_id,
                label={"pt-BR": "Vocabulário promovido"},
                label_search="vocabulário promovido",
                type="structured-vocabulary",
                homepage=None,
                owner_id=None,
                source="model",
            )
        )
        db.commit()

    anon = client_factory()
    # spec 08-workshop-picklists.md §1.3: `python -m fipm import-data` also
    # promotes every knowledge model's `inlineFers` as source="model" rows,
    # so the shared catalogue this query sees is not just the one row this
    # test inserted -- pass a limit generous enough to not depend on how
    # many other model-source FERs happen to exist (the default limit=50
    # is a UI page size, not a test isolation guarantee; see
    # test_source_model_row_found_among_many_others below).
    r = anon.get("/api/fers", params={"source": "model", "limit": 1000})
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert fer_id in ids

    # And it's findable by search too, not just by the explicit source filter.
    r2 = anon.get("/api/fers", params={"q": "promovido"})
    assert r2.status_code == 200
    assert fer_id in {item["id"] for item in r2.json()["items"]}


def test_source_model_row_found_among_many_others(client_factory):
    """Regression test: promoting a knowledge model's inlineFers (e.g. the
    CONFOA 2026 workshop drafts under data/knowledge-models/) can grow the
    source="model" catalogue well past the default page size. A caller
    filtering by source="model" alone (no search term) must still be able
    to reach any given row -- via limit/offset, not by relying on the
    catalogue being small -- so this seeds 60 decoy rows that sort before
    ours and asserts we can still page to it."""
    from fipm.db import SessionLocal
    from fipm.models import Fer

    fer_id = "https://fipm.example.org/fers/draft/dddddddddddddddd"
    with SessionLocal() as db:
        for i in range(60):
            label = f"aaa decoy vocabulary {i:03d}"
            db.add(
                Fer(
                    id=f"https://fipm.example.org/fers/draft/decoy{i:03d}",
                    label={"en": label},
                    label_search=label.lower(),
                    type="structured-vocabulary",
                    homepage=None,
                    owner_id=None,
                    source="model",
                )
            )
        db.add(
            Fer(
                id=fer_id,
                label={"en": "zzz target vocabulary"},
                label_search="zzz target vocabulary",
                type="structured-vocabulary",
                homepage=None,
                owner_id=None,
                source="model",
            )
        )
        db.commit()

    anon = client_factory()
    r = anon.get("/api/fers", params={"source": "model", "limit": 1000})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 61
    assert fer_id in {item["id"] for item in body["items"]}

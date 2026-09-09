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
    r = anon.get("/api/fers", params={"source": "model"})
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert fer_id in ids

    # And it's findable by search too, not just by the explicit source filter.
    r2 = anon.get("/api/fers", params={"q": "promovido"})
    assert r2.status_code == 200
    assert fer_id in {item["id"] for item in r2.json()["items"]}

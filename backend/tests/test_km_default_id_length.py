"""Review finding 10 (routers/knowledge_models._default_model_id): a fork's
default id starts from the source's own id, which can itself be up to
MODEL_ID_PATTERN's max 64 characters -- appending `-fork`, and possibly a
`-<n>` counter on collision, must not silently produce an id longer than the
pattern allows. `_default_model_id` truncates the base (never the suffix)
so the composed candidate always fits."""

from __future__ import annotations

from fipm.km_content import MODEL_ID_PATTERN
from fipm.models import KnowledgeModel


def _register(client, email: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correcthorsebattery", "displayName": "U"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_km(db_session, *, id_, version="1.0.0"):
    km = KnowledgeModel(
        id=id_,
        version=version,
        owner_id=None,
        visibility="public",
        status="published",
        license="CC0-1.0",
        source="test",
        title={"en": id_},
        description={"en": id_},
        changelog=[],
        content={"id": id_, "version": version, "sections": []},
        content_sha256="x",
    )
    db_session.add(km)
    db_session.commit()
    return km


def test_default_fork_id_of_max_length_source_is_truncated_to_fit(client, db_session):
    max_len_id = "a" * 64
    assert MODEL_ID_PATTERN.match(max_len_id)
    _make_km(db_session, id_=max_len_id)

    _register(client, "default-id-length-1@example.com")
    r = client.post(f"/api/knowledge-models/{max_len_id}/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]

    assert len(new_id) <= 64
    assert new_id.endswith("-fork")
    assert MODEL_ID_PATTERN.match(new_id)


def test_default_fork_id_with_counter_suffix_still_fits(client, db_session):
    max_len_id = "b" * 64
    _make_km(db_session, id_=max_len_id)
    # Pre-occupy the id `_default_model_id` would try first, forcing it to
    # fall through to the "-fork-2" counter branch.
    _make_km(db_session, id_=(max_len_id[: 64 - len("-fork")] + "-fork"), version="1.0.0")

    _register(client, "default-id-length-2@example.com")
    r = client.post(f"/api/knowledge-models/{max_len_id}/1.0.0/fork", json={})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]

    assert len(new_id) <= 64
    assert new_id.endswith("-fork-2")
    assert MODEL_ID_PATTERN.match(new_id)

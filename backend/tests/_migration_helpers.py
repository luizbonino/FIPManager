"""Shared scenario builder for spec 07-mail-and-migration.md §8 migration
acceptance tests (AC11-AC19): fork `test-km`, publish 1.0.0, answer three
questions, `new-version` to 1.1.0 with one `en` text edit, one added
question, one removed question, one hidden question and one answered
question split; publish 1.1.0. Mirrors `tests/fixtures/migration/*.json`
(same shape) so the diff behaviour matches `test_migration_diff_fixture.py`.

Not a test module itself (no `test_` prefix), so pytest doesn't collect it.
"""

from __future__ import annotations

from typing import Any

PRIVACY_VERSION = "test-v1"

OLD_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "findable",
        "title": {"en": "Findable"},
        "questions": [
            {
                "id": "F1-metadata",
                "text": {"en": "What identifiers do you use?"},
                "ferType": "identifier-service",
            },
            {
                "id": "F2",
                "text": {"en": "Which metadata schema do you use?"},
                "ferType": "metadata-schema",
            },
            {"id": "F3", "text": {"en": "Some F3 question"}, "ferType": "metadata-schema"},
        ],
    },
    {
        "id": "accessible",
        "title": {"en": "Accessible"},
        "questions": [
            {"id": "A2", "text": {"en": "Some A2 question"}, "ferType": "identifier-service"},
        ],
    },
]

NEW_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "findable",
        "title": {"en": "Findable"},
        "questions": [
            {
                "id": "F1-metadata",
                "text": {"en": "What identifiers do you use? (edited)"},
                "ferType": "identifier-service",
            },
            {
                "id": "F2-metadata",
                "text": {"en": "Metadata schema (metadata record)"},
                "ferType": "metadata-schema",
            },
            {
                "id": "F2-data",
                "text": {"en": "Metadata schema (data record)"},
                "ferType": "metadata-schema",
            },
            {
                "id": "F3",
                "text": {"en": "Some F3 question"},
                "ferType": "metadata-schema",
                "hidden": True,
            },
            {
                "id": "R1.3-data",
                "text": {"en": "A newly added question"},
                "ferType": "identifier-service",
            },
        ],
    },
    {"id": "accessible", "title": {"en": "Accessible"}, "questions": []},
]

# spec §8 AC11: "a FIP with answers on three questions" -- the split (F2),
# hidden (F3) and removed (A2) questions, so AC13's "the hidden question's
# answer is still in answers" and "the deleted question's answer is in
# orphanedAnswers" are both about *answered* questions. F1-metadata (the
# text-edited question) is deliberately left unanswered: AC12 only asserts
# its diff status/flags, never that it's answered.
DEFAULT_ANSWERS: list[dict[str, Any]] = [
    {
        "questionId": "F2",
        "declarations": [{"ferId": "https://w3id.org/np/dcat", "status": "current"}],
    },
    {
        "questionId": "F3",
        "declarations": [{"ferId": "https://w3id.org/np/dcat", "status": "current"}],
    },
    {
        "questionId": "A2",
        "declarations": [{"ferId": "https://w3id.org/np/orcid", "status": "current"}],
        "comment": "kept for provenance",
    },
]


def register(client, email: str, *, display_name: str = "Migrator") -> str:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": display_name,
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def publish_v1(client, km_id: str, *, sections: list[dict[str, Any]] | None = None) -> None:
    get1 = client.get(f"/api/knowledge-models/{km_id}/1.0.0")
    etag1 = get1.headers["etag"]
    put1 = client.put(
        f"/api/knowledge-models/{km_id}/1.0.0/content",
        headers={"If-Match": etag1},
        json={"sections": sections if sections is not None else OLD_SECTIONS},
    )
    assert put1.status_code == 200, put1.text
    pub1 = client.post(f"/api/knowledge-models/{km_id}/1.0.0/publish", json={"notes": "initial"})
    assert pub1.status_code == 200, pub1.text


def publish_v1_1(client, km_id: str, *, sections: list[dict[str, Any]] | None = None) -> str:
    nv = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
    assert nv.status_code == 201, nv.text
    new_version = nv.json()["version"]

    get2 = client.get(f"/api/knowledge-models/{km_id}/{new_version}")
    etag2 = get2.headers["etag"]
    put2 = client.put(
        f"/api/knowledge-models/{km_id}/{new_version}/content",
        headers={"If-Match": etag2},
        json={"sections": sections if sections is not None else NEW_SECTIONS},
    )
    assert put2.status_code == 200, put2.text

    pub2 = client.post(
        f"/api/knowledge-models/{km_id}/{new_version}/publish",
        json={"notes": "F2 split, A2 removed, F3 hidden, R1.3-data added"},
    )
    assert pub2.status_code == 200, pub2.text
    return new_version


def build_scenario(
    client,
    email_prefix: str,
    *,
    answers: list[dict[str, Any]] | None = None,
    visibility: str | None = None,
    session_id: str | None = None,
    join_code: str | None = None,
    publish_target: bool = True,
) -> dict[str, Any]:
    """Fork `test-km` -> publish 1.0.0 -> create a FIP -> `new-version` ->
    (edit + publish 1.1.0, unless `publish_target=False`). Returns
    `{km_id, fip_id, new_version}` (`new_version` is `None` when
    `publish_target=False`)."""
    register(client, f"{email_prefix}@example.com")

    fork = client.post(
        "/api/knowledge-models/test-km/1.0.0/fork", json={"newId": f"{email_prefix}-km"}
    )
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    publish_v1(client, km_id)

    fip_body: dict[str, Any] = {
        "questionnaireRef": {"id": km_id, "version": "1.0.0"},
        "answers": answers if answers is not None else DEFAULT_ANSWERS,
    }
    if visibility:
        fip_body["visibility"] = visibility
    if session_id:
        fip_body["sessionId"] = session_id
        fip_body["joinCode"] = join_code
    fip_r = client.post("/api/fips", json=fip_body)
    assert fip_r.status_code == 201, fip_r.text
    fip_json = fip_r.json()

    new_version = None
    if publish_target:
        new_version = publish_v1_1(client, km_id)
    else:
        nv = client.post(f"/api/knowledge-models/{km_id}/1.0.0/new-version", json={})
        assert nv.status_code == 201, nv.text

    return {
        "km_id": km_id,
        "fip_id": fip_json["id"],
        "edit_token": fip_json.get("editToken"),
        "new_version": new_version,
    }

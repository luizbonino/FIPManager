"""spec 08-workshop-picklists.md §6 AC10/AC11:
AC10: `POST /api/sessions` with three labelled refs returns them in order;
`questionnaireRef` echoes the first; a duplicate ref -> 400, a conflicting
`questionnaireRef` -> 400, a 90-char label -> 400.
AC11: `POST /api/sessions` with only `questionnaireRef` (a pre-v6 client
body) still returns 201 and a one-entry `questionnaireRefs` labelled with
the model's title."""

from __future__ import annotations


def _register(client, email: str) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text


def _publish_fork(client, new_id: str, title_en: str) -> None:
    fork = client.post("/api/knowledge-models/test-km/1.0.0/fork", json={"newId": new_id})
    assert fork.status_code == 201, fork.text
    patch = client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"title": {"en": title_en}})
    assert patch.status_code == 200, patch.text
    patch_vis = client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"visibility": "public"})
    assert patch_vis.status_code == 200, patch_vis.text
    pub = client.post(f"/api/knowledge-models/{new_id}/1.0.0/publish", json={"notes": "go"})
    assert pub.status_code == 200, pub.text


def test_three_labelled_refs_in_order_and_first_ref_echoed(client):
    _register(client, "ac08-10@example.com")
    _publish_fork(client, "ac0810-area-a", "Area A")
    _publish_fork(client, "ac0810-area-b", "Area B")
    _publish_fork(client, "ac0810-area-c", "Area C")

    body = {
        "title": "Multi-area session",
        "defaultLanguage": "en",
        "questionnaireRefs": [
            {"id": "ac0810-area-a", "version": "1.0.0", "label": {"pt-BR": "Área A"}},
            {"id": "ac0810-area-b", "version": "1.0.0", "label": {"pt-BR": "Área B"}},
            {"id": "ac0810-area-c", "version": "1.0.0", "label": {"pt-BR": "Área C"}},
        ],
    }
    r = client.post("/api/sessions", json=body)
    assert r.status_code == 201, r.text
    session = r.json()
    assert [ref["id"] for ref in session["questionnaireRefs"]] == [
        "ac0810-area-a",
        "ac0810-area-b",
        "ac0810-area-c",
    ]
    assert session["questionnaireRefs"][0]["label"] == {"pt-BR": "Área A"}
    assert session["questionnaireId"] == "ac0810-area-a"
    assert session["questionnaireVersion"] == "1.0.0"


def test_duplicate_ref_is_400(client):
    _register(client, "ac08-10b@example.com")
    _publish_fork(client, "ac0810b-area-a", "Area A")
    r = client.post(
        "/api/sessions",
        json={
            "title": "Dup session",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": "ac0810b-area-a", "version": "1.0.0", "label": {"en": "A"}},
                {"id": "ac0810b-area-a", "version": "1.0.0", "label": {"en": "A again"}},
            ],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "duplicate_questionnaire_ref"


def test_conflicting_questionnaire_ref_is_400(client):
    _register(client, "ac08-10c@example.com")
    _publish_fork(client, "ac0810c-area-a", "Area A")
    _publish_fork(client, "ac0810c-area-b", "Area B")
    r = client.post(
        "/api/sessions",
        json={
            "title": "Conflict session",
            "defaultLanguage": "en",
            "questionnaireRef": {"id": "ac0810c-area-b", "version": "1.0.0"},
            "questionnaireRefs": [
                {"id": "ac0810c-area-a", "version": "1.0.0", "label": {"en": "A"}},
            ],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "questionnaire_ref_conflict"


def test_90_char_label_is_400(client):
    _register(client, "ac08-10d@example.com")
    _publish_fork(client, "ac0810d-area-a", "Area A")
    r = client.post(
        "/api/sessions",
        json={
            "title": "Long label session",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": "ac0810d-area-a", "version": "1.0.0", "label": {"en": "x" * 90}},
            ],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_content"
    assert any(e["code"] == "too_long" for e in r.json()["errors"])


def test_pre_v6_body_with_only_questionnaire_ref_still_201s_with_derived_ref(client):
    _register(client, "ac08-11@example.com")
    r = client.post(
        "/api/sessions",
        json={
            "title": "Legacy session",
            "defaultLanguage": "en",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        },
    )
    assert r.status_code == 201, r.text
    session = r.json()
    assert len(session["questionnaireRefs"]) == 1
    ref = session["questionnaireRefs"][0]
    assert ref["id"] == "test-km"
    assert ref["version"] == "1.0.0"
    # test-km is public+published (fixture), so its title is anonymously
    # readable and used as the derived label.
    assert ref["label"] == {
        "en": "Test knowledge model",
        "pt-BR": "Modelo de conhecimento de teste",
    }
    assert ref["title"] == ref["label"]


def test_neither_ref_field_is_422(client):
    _register(client, "ac08-11b@example.com")
    r = client.post("/api/sessions", json={"title": "No ref session", "defaultLanguage": "en"})
    assert r.status_code == 422

"""spec 08-workshop-picklists.md §6 AC12: `POST /api/fips` into a three-ref
session succeeds for the second ref and 400s for an unlisted one;
`PATCH /api/sessions/{id}` replacing the refs 409s `session_has_fips` once
one FIP exists."""

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
    client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"title": {"en": title_en}})
    client.patch(f"/api/knowledge-models/{new_id}/1.0.0", json={"visibility": "public"})
    pub = client.post(f"/api/knowledge-models/{new_id}/1.0.0/publish", json={"notes": "go"})
    assert pub.status_code == 200, pub.text


def _create_three_ref_session(client, prefix: str) -> dict:
    _publish_fork(client, f"{prefix}-a", "Area A")
    _publish_fork(client, f"{prefix}-b", "Area B")
    _publish_fork(client, f"{prefix}-c", "Area C")
    r = client.post(
        "/api/sessions",
        json={
            "title": "Three area session",
            "defaultLanguage": "en",
            "questionnaireRefs": [
                {"id": f"{prefix}-a", "version": "1.0.0", "label": {"en": "A"}},
                {"id": f"{prefix}-b", "version": "1.0.0", "label": {"en": "B"}},
                {"id": f"{prefix}-c", "version": "1.0.0", "label": {"en": "C"}},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_fip_creation_succeeds_for_second_ref_and_400s_for_unlisted_ref(client_factory):
    owner = client_factory()
    _register(owner, "ac08-12a@example.com")
    session = _create_three_ref_session(owner, "ac0812a")

    participant = client_factory()
    ok = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "ac0812a-b", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["questionnaireId"] == "ac0812a-b"
    assert ok.json()["areaLabel"] == {"en": "B"}

    unlisted = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert unlisted.status_code == 400
    assert unlisted.json()["detail"] == "questionnaire_ref_mismatch"


def test_patch_refs_409s_once_a_fip_exists(client_factory):
    owner = client_factory()
    _register(owner, "ac08-12b@example.com")
    session = _create_three_ref_session(owner, "ac0812b")

    participant = client_factory()
    fip = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "ac0812b-a", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert fip.status_code == 201, fip.text

    patch = owner.patch(
        f"/api/sessions/{session['id']}",
        json={
            "questionnaireRefs": [
                {"id": "ac0812b-a", "version": "1.0.0", "label": {"en": "A only"}},
            ]
        },
    )
    assert patch.status_code == 409
    assert patch.json()["detail"] == "session_has_fips"


def test_patch_refs_succeeds_before_any_fip_exists(client_factory):
    owner = client_factory()
    _register(owner, "ac08-12c@example.com")
    session = _create_three_ref_session(owner, "ac0812c")

    patch = owner.patch(
        f"/api/sessions/{session['id']}",
        json={
            "questionnaireRefs": [
                {"id": "ac0812c-a", "version": "1.0.0", "label": {"en": "A fixed typo"}},
            ]
        },
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert len(body["questionnaireRefs"]) == 1
    assert body["questionnaireRefs"][0]["label"] == {"en": "A fixed typo"}
    assert body["questionnaireId"] == "ac0812c-a"

"""AC16 (spec 07-mail-and-migration.md §8): a FIP with `session_id` set ->
409 `session_version_pinned` on migrate while `migration-targets`/
`migration-preview` still return 200; after `POST /api/fips/{id}/claim` it
keeps `session_id` and stays pinned -- the pin is the session's, not the
owner's."""

from __future__ import annotations

from _migration_helpers import publish_v1, publish_v1_1, register

PRIVACY_VERSION = "test-v1"


def _build_session_scenario(client, client_factory, prefix: str):
    facilitator = client_factory()
    register(facilitator, f"{prefix}-facilitator@example.com")

    fork = facilitator.post(
        "/api/knowledge-models/test-km/1.0.0/fork", json={"newId": f"{prefix}-km"}
    )
    assert fork.status_code == 201, fork.text
    km_id = fork.json()["id"]
    # A fork starts private (spec 04 §1); a session-joinable model must be
    # readable by anonymous participants, so make it public before publish.
    vis = facilitator.patch(f"/api/knowledge-models/{km_id}/1.0.0", json={"visibility": "public"})
    assert vis.status_code == 200, vis.text
    publish_v1(facilitator, km_id)

    session_r = facilitator.post(
        "/api/sessions",
        json={
            "title": f"{prefix} session",
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert session_r.status_code == 201, session_r.text
    session = session_r.json()

    fip_r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": km_id, "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert fip_r.status_code == 201, fip_r.text
    fip = fip_r.json()

    publish_v1_1(facilitator, km_id)

    return {"km_id": km_id, "fip_id": fip["id"], "edit_token": fip["editToken"]}


def test_session_fip_migrate_is_pinned_but_targets_and_preview_work(client, client_factory):
    scenario = _build_session_scenario(client, client_factory, "mig16a")
    fip_id = scenario["fip_id"]
    headers = {"X-Edit-Token": scenario["edit_token"]}

    targets = client.get(f"/api/fips/{fip_id}/migration-targets", headers=headers)
    assert targets.status_code == 200, targets.text
    assert targets.json()["total"] == 1

    preview = client.get(f"/api/fips/{fip_id}/migration-preview?to=1.1.0", headers=headers)
    assert preview.status_code == 200, preview.text

    migrate = client.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"}, headers=headers)
    assert migrate.status_code == 409
    assert migrate.json()["detail"] == "session_version_pinned"


def test_pin_survives_claim(client, client_factory):
    scenario = _build_session_scenario(client, client_factory, "mig16b")
    fip_id = scenario["fip_id"]
    headers = {"X-Edit-Token": scenario["edit_token"]}

    claimant = client_factory()
    register(claimant, "mig16b-claimant@example.com")
    claimed = claimant.post(f"/api/fips/{fip_id}/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["ownerId"]
    assert claimed.json()["sessionId"] is not None

    migrate = claimant.post(f"/api/fips/{fip_id}/migrate", json={"to": "1.1.0"})
    assert migrate.status_code == 409
    assert migrate.json()["detail"] == "session_version_pinned"

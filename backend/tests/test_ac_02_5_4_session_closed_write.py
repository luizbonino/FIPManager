"""spec 02-core-flows.md §5.4 / §8 item 5: once a session is closed, an
anonymous FIP of that session refuses PATCH/DELETE with 409 session_closed
even with the correct edit token, unless the caller is the session owner or
an admin; reads (GET, both exports) stay 200; the session owner's own
cookie-authenticated PATCH still succeeds."""

from __future__ import annotations


def test_closed_session_rejects_anonymous_writes_but_not_owner_or_reads(client, client_factory):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "closed-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "closing session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    assert created.status_code == 201
    fip = created.json()
    fip_id = fip["id"]
    edit_token = fip["editToken"]

    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    patch_resp = participant.patch(
        f"/api/fips/{fip_id}",
        json={"license": "MIT"},
        headers={"X-Edit-Token": edit_token},
    )
    assert patch_resp.status_code == 409
    assert patch_resp.json()["detail"] == "session_closed"

    delete_resp = participant.delete(f"/api/fips/{fip_id}", headers={"X-Edit-Token": edit_token})
    assert delete_resp.status_code == 409
    assert delete_resp.json()["detail"] == "session_closed"

    # Reads are unaffected.
    assert participant.get(f"/api/fips/{fip_id}").status_code == 200
    assert participant.get(f"/api/fips/{fip_id}/export.json").status_code == 200
    assert participant.get(f"/api/fips/{fip_id}/export.csv").status_code == 200

    # The session owner's cookie-authenticated PATCH still works.
    owner_patch = facilitator.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert owner_patch.status_code == 200
    assert owner_patch.json()["license"] == "MIT"

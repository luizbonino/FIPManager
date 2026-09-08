"""End-to-end anonymous-session flow: a facilitator creates a session, an
anonymous participant discovers it via the public join-by-code lookup, joins
by creating a FIP with the sessionId + joinCode, edits it with the edit
token, and a signed-in user later claims it. Exercises AC6, AC7 and AC9
together as one continuous flow rather than as isolated scenarios."""

from __future__ import annotations


def test_full_anonymous_session_flow(client, client_factory):
    # 1. Facilitator signs in and creates an open session.
    facilitator = client_factory()
    reg = facilitator.post(
        "/api/auth/register",
        json={
            "email": "flow-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "Facilitator",
        },
    )
    assert reg.status_code == 201

    session_resp = facilitator.post(
        "/api/sessions",
        json={
            "title": "Flow workshop",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert session_resp.status_code == 201
    session = session_resp.json()
    assert session["status"] == "open"

    # 2. An anonymous participant discovers the session by its join code
    # alone (no session id needed for this read-only lookup).
    anon = client_factory()
    by_code = anon.get(f"/api/sessions/by-code/{session['joinCode']}")
    assert by_code.status_code == 200
    public_session = by_code.json()
    assert public_session["id"] == session["id"]
    assert public_session["questionnaireRef"]["id"] == "test-km"

    # 3. The participant joins by creating a FIP with sessionId + joinCode.
    create = anon.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
            "answers": [
                {
                    "questionId": "F1-metadata",
                    "declarations": [{"ferId": "https://w3id.org/np/doi", "status": "current"}],
                }
            ],
        },
    )
    assert create.status_code == 201
    fip = create.json()
    fip_id = fip["id"]
    edit_token = fip["editToken"]
    assert fip["ownerId"] is None
    assert fip["sessionId"] == session["id"]
    assert edit_token

    # The FIP shows up in the facilitator's session listing.
    session_fips = facilitator.get(f"/api/sessions/{session['id']}/fips")
    assert session_fips.status_code == 200
    assert any(f["id"] == fip_id for f in session_fips.json()["items"])

    # 4. PATCH without the token is rejected; with the correct token it
    # succeeds, and the token itself is never echoed back.
    no_token = anon.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "edit_token_required"

    wrong_token = anon.patch(
        f"/api/fips/{fip_id}",
        json={"license": "MIT"},
        headers={"X-Edit-Token": "not-the-token"},
    )
    assert wrong_token.status_code == 403

    patched = anon.patch(
        f"/api/fips/{fip_id}",
        json={"license": "MIT"},
        headers={"X-Edit-Token": edit_token},
    )
    assert patched.status_code == 200
    assert patched.json()["license"] == "MIT"
    assert "editToken" not in patched.json()

    # 5. A different signed-in user claims the FIP with the edit token.
    claimant = client_factory()
    claimant_reg = claimant.post(
        "/api/auth/register",
        json={
            "email": "flow-claimant@example.com",
            "password": "correcthorsebattery",
            "displayName": "Claimant",
        },
    )
    assert claimant_reg.status_code == 201

    claim = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token})
    assert claim.status_code == 200
    claimed = claim.json()
    assert claimed["ownerId"] == claimant_reg.json()["id"]

    # The now-void token no longer works, but the new owner's cookie does.
    stale = anon.patch(
        f"/api/fips/{fip_id}",
        json={"license": "CC0-1.0"},
        headers={"X-Edit-Token": edit_token},
    )
    assert stale.status_code == 403

    owner_patch = claimant.patch(f"/api/fips/{fip_id}", json={"license": "CC0-1.0"})
    assert owner_patch.status_code == 200
    assert owner_patch.json()["license"] == "CC0-1.0"

    # Claiming again (already owned) is a conflict.
    second_claimant = client_factory()
    second_claimant.post(
        "/api/auth/register",
        json={
            "email": "flow-second-claimant@example.com",
            "password": "correcthorsebattery",
            "displayName": "Second",
        },
    )
    already = second_claimant.post(
        f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token}
    )
    assert already.status_code == 409

    # The FIP now shows up in the claimant's own FIP list.
    my_fips = claimant.get("/api/me/fips")
    assert my_fips.status_code == 200
    assert any(f["id"] == fip_id for f in my_fips.json()["items"])

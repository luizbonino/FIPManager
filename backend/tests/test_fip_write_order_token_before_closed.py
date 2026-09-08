"""Review finding 7: _authorize_fip_write must check the edit token before
checking whether the session is closed, so a caller with no (or the wrong)
token gets 403 edit_token_required rather than 409 session_closed -- the
closed-session detail must not leak to callers who never proved they hold a
valid token."""

from __future__ import annotations


def test_missing_token_is_403_not_409_even_when_session_closed(client_factory):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "order-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "order session",
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
    fip_id = created.json()["id"]

    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    # No token at all: 403, not 409 -- the caller never proved they hold a
    # valid edit token, so the session's closed status is not revealed.
    no_token = participant.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "edit_token_required"

    # Wrong token: same 403, same reasoning.
    wrong_token = participant.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": "not-the-token"}
    )
    assert wrong_token.status_code == 403
    assert wrong_token.json()["detail"] == "edit_token_required"

    # DELETE follows the same order.
    no_token_delete = participant.delete(f"/api/fips/{fip_id}")
    assert no_token_delete.status_code == 403
    assert no_token_delete.json()["detail"] == "edit_token_required"

    # The *correct* token still surfaces 409 session_closed once the token
    # check passes.
    correct_token = created.json()["editToken"]
    with_token = participant.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": correct_token}
    )
    assert with_token.status_code == 409
    assert with_token.json()["detail"] == "session_closed"

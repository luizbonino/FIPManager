"""spec 05-v1-completion.md §6 / §8 AC14 (backend half): "The backend already
lets a session owner write any FIP of their session, before and after close
(fips._authorize_fip_write); only the UI was missing." This confirms that
still holds for an *owned* (claimed) FIP, not just an anonymous one -- the
session-owner branch inside the owned-FIP path of _authorize_fip_write --
both before and after the session closes."""

from __future__ import annotations

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "U",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_facilitator_can_write_claimed_fip_before_and_after_close(client_factory):
    facilitator = client_factory()
    _register(facilitator, "ac05-14-facilitator@example.com")
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "ac05-14 session",
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
    fip = created.json()
    fip_id, token = fip["id"], fip["editToken"]

    claimant = client_factory()
    _register(claimant, "ac05-14-claimant@example.com")
    claimed = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": token})
    assert claimed.status_code == 200
    assert claimed.json()["ownerId"]

    # Facilitator (session owner, not the FIP's owner) can still write it.
    before_close = facilitator.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert before_close.status_code == 200

    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    after_close = facilitator.patch(f"/api/fips/{fip_id}", json={"license": "CC0-1.0"})
    assert after_close.status_code == 200
    assert after_close.json()["license"] == "CC0-1.0"

    # A stranger (neither facilitator nor owner) is still refused.
    stranger = client_factory()
    _register(stranger, "ac05-14-stranger@example.com")
    stranger_patch = stranger.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert stranger_patch.status_code in (403, 404)

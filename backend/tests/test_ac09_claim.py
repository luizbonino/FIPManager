"""AC9: a signed-in user presenting the correct edit token claims an anonymous
FIP (200, ownerId set); a subsequent PATCH with the now-void token is 403 while
the owner's cookie works; claiming an already-owned FIP returns 409."""

from __future__ import annotations


def _make_anonymous_fip(client, client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac9-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ac9",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    return client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    ).json()


def test_claim_flow(client, client_factory):
    fip = _make_anonymous_fip(client, client_factory)
    fip_id, token = fip["id"], fip["editToken"]

    claimant = client_factory()
    claimant.post(
        "/api/auth/register",
        json={
            "email": "ac9-claimant@example.com",
            "password": "correcthorsebattery",
            "displayName": "Claimant",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    claimed = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": token})
    assert claimed.status_code == 200
    assert claimed.json()["ownerId"]

    stale = client_factory()
    stale_patch = stale.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": token}
    )
    assert stale_patch.status_code == 403

    owner_patch = claimant.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert owner_patch.status_code == 200

    second_claimant = client_factory()
    second_claimant.post(
        "/api/auth/register",
        json={
            "email": "ac9-second@example.com",
            "password": "correcthorsebattery",
            "displayName": "Second",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    already = second_claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": token})
    assert already.status_code == 409

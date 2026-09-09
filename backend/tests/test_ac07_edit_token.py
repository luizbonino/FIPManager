"""AC7: PATCH on an anonymous FIP requires X-Edit-Token; missing/wrong -> 403,
correct -> 200; no endpoint ever returns the token again."""

from __future__ import annotations


def _make_anonymous_fip(client, client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "ac7-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ac7",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    fip = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    ).json()
    return fip


def test_patch_requires_correct_edit_token(client, client_factory):
    fip = _make_anonymous_fip(client, client_factory)
    fip_id, token = fip["id"], fip["editToken"]

    no_token = client.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert no_token.status_code == 403
    assert no_token.json()["detail"] == "edit_token_required"

    wrong_token = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": "wrong-token"}
    )
    assert wrong_token.status_code == 403

    ok = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": token}
    )
    assert ok.status_code == 200
    assert ok.json()["license"] == "MIT"
    assert "editToken" not in ok.json()

    get_after = client.get(f"/api/fips/{fip_id}")
    assert "editToken" not in get_after.json()

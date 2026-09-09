"""Review finding 10: edit-token hashes and join codes are compared with
secrets.compare_digest instead of `==`. Functionally this must still reject
any wrong value, including ones of a different length than the real secret
(a naive constant-time helper can mishandle unequal-length inputs, e.g. by
raising instead of returning False)."""

from __future__ import annotations


def test_edit_token_of_different_length_is_rejected_not_erroring(client, client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "ctc-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ctc",
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
    fip_id, real_token = fip["id"], fip["editToken"]

    too_short = real_token[:5]
    too_long = real_token + "extra-trailing-bytes"

    r_short = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": too_short}
    )
    assert r_short.status_code == 403

    r_long = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": too_long}
    )
    assert r_long.status_code == 403

    r_ok = client.patch(
        f"/api/fips/{fip_id}", json={"license": "MIT"}, headers={"X-Edit-Token": real_token}
    )
    assert r_ok.status_code == 200


def test_join_code_of_different_length_is_rejected_not_erroring(client, client_factory):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": "ctc-join-owner@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = owner.post(
        "/api/sessions",
        json={
            "title": "ctc-join",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    r = client.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"] + "TOOLONG",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "invalid_join_code"

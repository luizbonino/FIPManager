"""Review finding 8: a session owner can already PATCH/DELETE an anonymous
FIP in their own session without the edit token; the same rule must apply to
reads (GET and both export endpoints), not just writes."""

from __future__ import annotations


def test_session_owner_can_read_and_export_without_edit_token(client, client_factory):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": "sessread-facilitator@example.com",
            "password": "correcthorsebattery",
            "displayName": "F",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "sessread",
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
            "visibility": "private",
        },
    )
    assert created.status_code == 201
    fip_id = created.json()["id"]

    # The facilitator (session owner) never received the edit token, yet can
    # read the FIP and export it, because they own the session.
    get_resp = facilitator.get(f"/api/fips/{fip_id}")
    assert get_resp.status_code == 200

    export_json = facilitator.get(f"/api/fips/{fip_id}/export.json")
    assert export_json.status_code == 200

    export_csv = facilitator.get(f"/api/fips/{fip_id}/export.csv")
    assert export_csv.status_code == 200

    # A third party (not the session owner, no token) still gets 404.
    stranger = client_factory()
    stranger.post(
        "/api/auth/register",
        json={
            "email": "sessread-stranger@example.com",
            "password": "correcthorsebattery",
            "displayName": "S",
        },
    )
    assert stranger.get(f"/api/fips/{fip_id}").status_code == 404

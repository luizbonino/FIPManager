"""Review finding 2: a token holder cannot claim a FIP whose session is
closed (409 session_closed, no owner/admin exemption — claiming is only for
token holders); and a FIP claimed while its session was open stays frozen
for its new owner once the session later closes, unless the caller is the
session owner or an admin."""

from __future__ import annotations


def _facilitator_and_session(client_factory, email):
    facilitator = client_factory()
    facilitator.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "F",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    session = facilitator.post(
        "/api/sessions",
        json={
            "title": "claim-closed",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()
    return facilitator, session


def test_claim_rejected_when_session_already_closed(client_factory):
    facilitator, session = _facilitator_and_session(client_factory, "claimclosed-f1@example.com")

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
    fip_id, edit_token = fip["id"], fip["editToken"]

    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    claimant = client_factory()
    claimant.post(
        "/api/auth/register",
        json={
            "email": "claimclosed-claimant1@example.com",
            "password": "correcthorsebattery",
            "displayName": "C",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    claim = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token})
    assert claim.status_code == 409
    assert claim.json()["detail"] == "session_closed"

    # Not claimed: still ownerless.
    still_anon = facilitator.get(f"/api/sessions/{session['id']}/fips").json()
    assert any(f["id"] == fip_id and f["ownerId"] is None for f in still_anon["items"])


def test_claim_rejected_even_for_admin_or_session_owner(client_factory, db_session):
    from fipm.models import User

    facilitator, session = _facilitator_and_session(client_factory, "claimclosed-f2@example.com")

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    fip_id, edit_token = created.json()["id"], created.json()["editToken"]

    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    # The facilitator (session owner) themself cannot claim into a closed
    # session either -- claiming has no owner/admin exemption.
    owner_claim = facilitator.post(
        f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token}
    )
    assert owner_claim.status_code == 409
    assert owner_claim.json()["detail"] == "session_closed"

    admin = client_factory()
    reg = admin.post(
        "/api/auth/register",
        json={
            "email": "claimclosed-admin@example.com",
            "password": "correcthorsebattery",
            "displayName": "Admin",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    admin_id = reg.json()["id"]
    db_session.query(User).filter(User.id == admin_id).update({"role": "admin"})
    db_session.commit()

    admin_claim = admin.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token})
    assert admin_claim.status_code == 409
    assert admin_claim.json()["detail"] == "session_closed"


def test_claimed_fip_frozen_once_its_session_closes(client_factory, db_session):
    from fipm.models import User

    facilitator, session = _facilitator_and_session(client_factory, "claimclosed-f3@example.com")

    participant = client_factory()
    created = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    )
    fip_id, edit_token = created.json()["id"], created.json()["editToken"]

    claimant = client_factory()
    claimant.post(
        "/api/auth/register",
        json={
            "email": "claimclosed-claimant2@example.com",
            "password": "correcthorsebattery",
            "displayName": "C",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    claim = claimant.post(f"/api/fips/{fip_id}/claim", headers={"X-Edit-Token": edit_token})
    assert claim.status_code == 200
    assert claim.json()["ownerId"]

    # Session closes after the claim.
    closed = facilitator.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    # The new owner is frozen out by their own claimed-but-now-closed FIP.
    frozen_patch = claimant.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert frozen_patch.status_code == 409
    assert frozen_patch.json()["detail"] == "session_closed"

    frozen_delete = claimant.delete(f"/api/fips/{fip_id}")
    assert frozen_delete.status_code == 409
    assert frozen_delete.json()["detail"] == "session_closed"

    # Reads still work for the owner.
    assert claimant.get(f"/api/fips/{fip_id}").status_code == 200

    # The session owner (facilitator) is exempt from the freeze.
    owner_patch = facilitator.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert owner_patch.status_code == 200
    assert owner_patch.json()["license"] == "MIT"

    # An admin is exempt from the freeze too.
    admin = client_factory()
    reg = admin.post(
        "/api/auth/register",
        json={
            "email": "claimclosed-admin2@example.com",
            "password": "correcthorsebattery",
            "displayName": "Admin",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    admin_id = reg.json()["id"]
    db_session.query(User).filter(User.id == admin_id).update({"role": "admin"})
    db_session.commit()

    admin_patch = admin.patch(f"/api/fips/{fip_id}", json={"license": "CC0-1.0"})
    assert admin_patch.status_code == 200
    assert admin_patch.json()["license"] == "CC0-1.0"

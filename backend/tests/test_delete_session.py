"""Review finding 5: DELETE /api/sessions/{id} (owner or admin, 404 for
anyone else/anonymous like every other session route). Deletes the session
itself, deletes its anonymous (never-claimed, owner_id NULL) FIPs, detaches
its claimed/owned FIPs (session_id -> NULL, the FIP itself survives under
its owner), and leaves feedback referencing the session or its deleted FIPs
in place with sessionId/fipId nulled by the existing
ondelete="SET NULL" foreign keys."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import Feedback, Fip, WorkshopSession

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


def _make_session(client, title):
    r = client.post(
        "/api/sessions",
        json={
            "title": title,
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_session_404_for_anonymous_and_non_owner(client, client_factory):
    _register(client, "delsession-owner@example.com")
    session = _make_session(client, "owner's session")

    anon_delete = client_factory().delete(f"/api/sessions/{session['id']}")
    assert anon_delete.status_code == 401  # require_user: no session cookie at all

    stranger = client_factory()
    _register(stranger, "delsession-stranger@example.com")
    stranger_delete = stranger.delete(f"/api/sessions/{session['id']}")
    assert stranger_delete.status_code == 404

    with SessionLocal() as db:
        assert db.get(WorkshopSession, session["id"]) is not None  # still there


def test_delete_session_deletes_anonymous_fips_detaches_owned_fips_and_nulls_feedback(
    client, client_factory
):
    _register(client, "delsession-owner2@example.com")
    session = _make_session(client, "session to delete")

    # An anonymous (never-claimed) participant FIP.
    anon_participant = client_factory()
    anon_fip = anon_participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    ).json()

    # A claimed (owned) participant FIP.
    claimant = client_factory()
    _register(claimant, "delsession-claimant@example.com")
    claimed_fip = claimant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    ).json()
    claim_resp = claimant.post(
        f"/api/fips/{claimed_fip['id']}/claim", headers={"X-Edit-Token": claimed_fip["editToken"]}
    )
    assert claim_resp.status_code == 200

    # Feedback referencing the session directly, and feedback referencing
    # one of its FIPs (the anonymous one, so it disappears too).
    session_feedback = client_factory().post(
        "/api/feedback",
        json={"q1": 5, "q2": 5, "q3": 5, "comment": "session-level", "sessionId": session["id"]},
    )
    assert session_feedback.status_code == 201
    fip_feedback = client_factory().post(
        "/api/feedback",
        json={"q1": 4, "q2": 4, "q3": 4, "comment": "fip-level", "fipId": anon_fip["id"]},
    )
    assert fip_feedback.status_code == 201

    delete_resp = client.delete(f"/api/sessions/{session['id']}")
    assert delete_resp.status_code == 204
    assert delete_resp.content == b""

    with SessionLocal() as db:
        assert db.get(WorkshopSession, session["id"]) is None  # session gone

        assert db.get(Fip, anon_fip["id"]) is None  # anonymous FIP deleted outright

        surviving = db.get(Fip, claimed_fip["id"])
        assert surviving is not None  # claimed FIP survives
        assert surviving.session_id is None  # but detached from the deleted session
        assert surviving.owner_id is not None

        session_row = db.query(Feedback).filter(Feedback.comment == "session-level").one()
        assert session_row.session_id is None  # nulled, not deleted

        fip_row = db.query(Feedback).filter(Feedback.comment == "fip-level").one()
        assert fip_row.fip_id is None  # nulled, not deleted (the FIP itself was)

    # The claimed FIP is still reachable by its owner after the session's gone.
    still_reachable = claimant.get(f"/api/fips/{claimed_fip['id']}")
    assert still_reachable.status_code == 200


def test_admin_can_delete_a_session_they_do_not_own(client, client_factory):
    from fipm.models import User

    _register(client, "delsession-owner3@example.com")
    session = _make_session(client, "admin-deletable session")

    admin = client_factory()
    _register(admin, "delsession-admin@example.com")
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "delsession-admin@example.com").one()
        u.role = "admin"
        db.commit()

    r = admin.delete(f"/api/sessions/{session['id']}")
    assert r.status_code == 204
    with SessionLocal() as db:
        assert db.get(WorkshopSession, session["id"]) is None

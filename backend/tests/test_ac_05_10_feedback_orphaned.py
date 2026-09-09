"""AC10 (spec 05-v1-completion.md §8): deleting a session (or a FIP) leaves
its feedback rows with sessionId/fipId NULL (SQLite ON DELETE SET NULL), and
its FIPs' feedback stays exportable from the CSV route -- a feedback row
that carries both a fipId and its session's sessionId keeps showing up in
that session's feedback.csv after the FIP itself is deleted, because its
sessionId (untouched by the FIP deletion) still resolves."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import Feedback

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


def test_deleting_fip_nulls_fip_id_but_session_feedback_stays_exportable(client, client_factory):
    _register(client, "ac05-10-owner@example.com")
    session = client.post(
        "/api/sessions",
        json={
            "title": "ac05-10 session",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    participant = client_factory()
    fip = participant.post(
        "/api/fips",
        json={
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "sessionId": session["id"],
            "joinCode": session["joinCode"],
        },
    ).json()

    posted = participant.post(
        "/api/feedback",
        json={
            "q1": 4,
            "q2": 4,
            "q3": 4,
            "comment": "orphan-check",
            "sessionId": session["id"],
            "fipId": fip["id"],
        },
    )
    assert posted.status_code == 201

    delete_resp = participant.delete(
        f"/api/fips/{fip['id']}", headers={"X-Edit-Token": fip["editToken"]}
    )
    assert delete_resp.status_code == 204

    with SessionLocal() as db:
        row = db.query(Feedback).filter(Feedback.comment == "orphan-check").one()
        assert row.fip_id is None
        assert row.session_id == session["id"]

    csv_after_fip_delete = client.get(f"/api/sessions/{session['id']}/feedback.csv")
    assert csv_after_fip_delete.status_code == 200
    assert b"orphan-check" in csv_after_fip_delete.content


def test_deleting_session_nulls_session_id(client, client_factory):
    _register(client, "ac05-10-session-owner@example.com")
    session = client.post(
        "/api/sessions",
        json={
            "title": "ac05-10 to delete",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    ).json()

    posted = client_factory().post(
        "/api/feedback",
        json={"q1": 3, "q2": 3, "q3": 3, "comment": "will-be-orphaned", "sessionId": session["id"]},
    )
    assert posted.status_code == 201

    with SessionLocal() as db:
        from fipm.models import WorkshopSession

        row = db.get(WorkshopSession, session["id"])
        db.delete(row)
        db.commit()

    with SessionLocal() as db:
        feedback_row = db.query(Feedback).filter(Feedback.comment == "will-be-orphaned").one()
        assert feedback_row.session_id is None

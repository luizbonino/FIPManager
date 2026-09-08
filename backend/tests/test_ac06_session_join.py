"""AC6: an anonymous client can POST /api/fips with a valid sessionId + joinCode
for an open session (editToken present exactly once); a closed session returns
409, a wrong joinCode returns 403."""

from __future__ import annotations


def _make_session(client_factory, owner_email):
    owner = client_factory()
    owner.post(
        "/api/auth/register",
        json={
            "email": owner_email,
            "password": "correcthorsebattery",
            "displayName": "Facilitator",
        },
    )
    r = owner.post(
        "/api/sessions",
        json={
            "title": "AC6 workshop",
            "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
            "defaultLanguage": "en",
        },
    )
    assert r.status_code == 201
    return owner, r.json()


def test_anonymous_fip_in_open_session(client, client_factory):
    _owner, session = _make_session(client_factory, "ac6-owner@example.com")

    body = {
        "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        "sessionId": session["id"],
        "joinCode": session["joinCode"],
    }
    r = client.post("/api/fips", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["ownerId"] is None
    assert data["sessionId"] == session["id"]
    assert data["editToken"]


def test_wrong_join_code_returns_403(client, client_factory):
    _owner, session = _make_session(client_factory, "ac6-owner2@example.com")
    body = {
        "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        "sessionId": session["id"],
        "joinCode": "WRONG1",
    }
    r = client.post("/api/fips", json=body)
    assert r.status_code == 403


def test_closed_session_returns_409(client, client_factory):
    owner, session = _make_session(client_factory, "ac6-owner3@example.com")
    closed = owner.patch(f"/api/sessions/{session['id']}", json={"status": "closed"})
    assert closed.status_code == 200

    body = {
        "questionnaireRef": {"id": "test-km", "version": "1.0.0"},
        "sessionId": session["id"],
        "joinCode": session["joinCode"],
    }
    r = client.post("/api/fips", json=body)
    assert r.status_code == 409

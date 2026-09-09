"""AC12: a state-changing request without Origin/Referer, or with a foreign
Origin, returns 403 csrf_failed; the same request with the app's own Origin
succeeds. GET requests are unaffected."""

from __future__ import annotations


def test_csrf_rejected_without_origin_and_with_foreign_origin(raw_client, settings):
    no_origin = raw_client.post(
        "/api/auth/register",
        json={
            "email": "ac12-a@example.com",
            "password": "correcthorsebattery",
            "displayName": "A",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert no_origin.status_code == 403
    assert no_origin.json()["detail"] == "csrf_failed"

    foreign_origin = raw_client.post(
        "/api/auth/register",
        json={
            "email": "ac12-b@example.com",
            "password": "correcthorsebattery",
            "displayName": "B",
            "privacyAcceptedVersion": "test-v1",
        },
        headers={"origin": "https://evil.example.com"},
    )
    assert foreign_origin.status_code == 403
    assert foreign_origin.json()["detail"] == "csrf_failed"

    same_origin = raw_client.post(
        "/api/auth/register",
        json={
            "email": "ac12-c@example.com",
            "password": "correcthorsebattery",
            "displayName": "C",
            "privacyAcceptedVersion": "test-v1",
        },
        headers={"origin": settings.base_url},
    )
    assert same_origin.status_code == 201


def test_csrf_does_not_affect_get(raw_client):
    r = raw_client.get("/api/health")
    assert r.status_code == 200


def test_csrf_failure_wins_over_password_change_required(client, raw_client, settings):
    """Review finding 9: a request that fails both the CSRF check and the
    must_change_password gate gets 403 csrf_failed, not
    password_change_required -- csrf_middleware must run first
    (outermost), so its rejection short-circuits before
    password_change_middleware ever runs. `raw_client` shares no cookie jar
    with `client`, so it's driven through `client`'s cookies explicitly."""
    from fipm.db import SessionLocal
    from fipm.models import User

    r = client.post(
        "/api/auth/register",
        json={
            "email": "ac12-csrf-wins@example.com",
            "password": "correcthorsebattery",
            "displayName": "CSRF Wins",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201, r.text

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "ac12-csrf-wins@example.com").one()
        user.must_change_password = True
        db.commit()

    session_cookie = client.cookies.get("fipm_session")
    assert session_cookie

    # Same flagged session cookie, but no Origin/Referer at all: csrf_failed
    # must win over password_change_required.
    raw_client.cookies.set("fipm_session", session_cookie)
    both_fail = raw_client.patch("/api/fips/doesnotexist", json={"license": "MIT"})
    assert both_fail.status_code == 403
    assert both_fail.json()["detail"] == "csrf_failed"

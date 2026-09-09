"""AC3 (spec 05-v1-completion.md §8): a user with mustChangePassword gets
403 password_change_required on PATCH /api/fips/{id} but 200 on
GET /api/auth/me; POST /api/auth/password succeeds, clears the flag, and the
same PATCH then returns 200. Also covers the exempted /api/auth/logout
route staying open."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import User

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


def _force_must_change_password(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.must_change_password = True
        db.commit()


def test_flagged_user_blocked_on_write_but_not_on_get_or_password_change(client):
    user = _register(client, "ac05-3-user@example.com")
    fip = client.post(
        "/api/fips", json={"questionnaireRef": {"id": "test-km", "version": "1.0.0"}}
    ).json()
    fip_id = fip["id"]

    _force_must_change_password("ac05-3-user@example.com")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["mustChangePassword"] is True

    blocked = client.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password_change_required"

    changed = client.post(
        "/api/auth/password",
        json={"currentPassword": "correcthorsebattery", "newPassword": "brandnewpassword1"},
    )
    assert changed.status_code == 204

    me_after = client.get("/api/auth/me")
    assert me_after.json()["mustChangePassword"] is False

    allowed = client.patch(f"/api/fips/{fip_id}", json={"license": "MIT"})
    assert allowed.status_code == 200

    assert user["id"]  # sanity: registration succeeded


def test_flagged_user_can_still_logout(client):
    _register(client, "ac05-3-logout@example.com")
    _force_must_change_password("ac05-3-logout@example.com")

    r = client.post("/api/auth/logout")
    assert r.status_code == 204


def test_flagged_user_can_still_login_and_register(client):
    """Review finding 3: /api/auth/login and /api/auth/register are exempt
    from password_change_middleware -- a stale cookie for a must-change
    account must not block logging into a *different* account, or
    registering a brand new one, with an unrelated 403
    password_change_required."""
    _register(client, "ac05-3-relogin@example.com")
    _force_must_change_password("ac05-3-relogin@example.com")

    # Re-submitting the login form for the still-flagged account: reachable,
    # not swallowed by the password-change gate (the temp password is wrong
    # here, so this is a 401, never a 403 password_change_required).
    relogin = client.post(
        "/api/auth/login",
        json={"email": "ac05-3-relogin@example.com", "password": "wrong-password"},
    )
    assert relogin.status_code == 401

    register_another = client.post(
        "/api/auth/register",
        json={
            "email": "ac05-3-another@example.com",
            "password": "correcthorsebattery",
            "displayName": "Another",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert register_another.status_code == 201

"""AC2 (spec 05-v1-completion.md §8): POST /api/admin/users/{id}/reset-
password returns a 12-char temporaryPassword; the old password then fails
login and the temporary one succeeds, every pre-existing auth_sessions row
of that user is gone, and the same call on the admin's own id returns
400 cannot_reset_self."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import AuthSession, User

PRIVACY_VERSION = "test-v1"
_ORIGINAL_PASSWORD = "correcthorsebattery"


def _register(client, email, display_name="U"):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": _ORIGINAL_PASSWORD,
            "displayName": display_name,
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _promote_to_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()


def test_reset_password_rotates_credentials_and_revokes_sessions(client_factory):
    admin = client_factory()
    admin_user = _register(admin, "ac05-2-admin@example.com")
    _promote_to_admin("ac05-2-admin@example.com")

    target = client_factory()
    target_user = _register(target, "ac05-2-target@example.com")
    target_id = target_user["id"]

    # A second signed-in session for the same target user, to prove it's
    # revoked too.
    target_second = client_factory()
    target_second.post(
        "/api/auth/login",
        json={"email": "ac05-2-target@example.com", "password": _ORIGINAL_PASSWORD},
    )

    with SessionLocal() as db:
        sessions_before = db.query(AuthSession).filter(AuthSession.user_id == target_id).count()
    assert sessions_before >= 2

    r = admin.post(f"/api/admin/users/{target_id}/reset-password")
    assert r.status_code == 200
    temp_password = r.json()["temporaryPassword"]
    assert len(temp_password) == 12
    # Crockford base32: no I/L/O/U.
    assert not (set(temp_password.upper()) & {"I", "L", "O", "U"})

    with SessionLocal() as db:
        sessions_after = db.query(AuthSession).filter(AuthSession.user_id == target_id).count()
    assert sessions_after == 0

    old_login = client_factory().post(
        "/api/auth/login",
        json={"email": "ac05-2-target@example.com", "password": _ORIGINAL_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = client_factory().post(
        "/api/auth/login", json={"email": "ac05-2-target@example.com", "password": temp_password}
    )
    assert new_login.status_code == 200
    assert new_login.json()["mustChangePassword"] is True

    self_reset = admin.post(f"/api/admin/users/{admin_user['id']}/reset-password")
    assert self_reset.status_code == 400
    assert self_reset.json()["detail"] == "cannot_reset_self"

"""AC6/AC7 (spec 07-mail-and-migration.md §7): `POST /api/auth/password-reset/
confirm` with a valid token and a 12-char password -> 204; the old password
then fails login (401) and the new one succeeds; every pre-existing
`auth_sessions` row is gone (a cookie captured before the reset returns 401
on `GET /api/auth/me`); `email_verified_at` is set although no verify link
was clicked. Replay -> 400 `invalid_token`, password unchanged; past its 1h
TTL -> 410 `token_expired`; a second reset token deletes the first unused
one (row count 1). A password-changed notice is queued after a successful
confirm (spec §1)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from fipm.ids import hash_token
from fipm.models import EmailToken, User

PRIVACY_VERSION = "test-v1"
OLD_PASSWORD = "correcthorsebattery"
NEW_PASSWORD = "brandnewpassword12"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": OLD_PASSWORD,
            "displayName": "C",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text


def _issue_reset_token(client, email, caplog) -> str:
    caplog.clear()
    r = client.post("/api/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202
    message = next(rec for rec in caplog.records if rec.name == "fipm.mail").getMessage()
    return re.search(r"/reset-password\?token=(\S+)", message).group(1)


def test_confirm_resets_password_revokes_sessions_and_verifies_email(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    email = "ac07-confirm-a@example.com"
    _register(client, email)

    # A cookie captured before the reset.
    pre_reset_cookie = client.cookies.get("fipm_session")
    assert pre_reset_cookie is not None
    me_before = client.get("/api/auth/me")
    assert me_before.status_code == 200

    token = _issue_reset_token(client, email, caplog)
    caplog.clear()
    r = client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "newPassword": NEW_PASSWORD}
    )
    assert r.status_code == 204

    # Password-changed notice queued.
    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert any("password" in rec.getMessage().lower() for rec in mail_records)

    # The pre-reset cookie is dead.
    still_using_old_cookie = client.get("/api/auth/me", cookies={"fipm_session": pre_reset_cookie})
    assert still_using_old_cookie.status_code == 401

    old_login = client.post("/api/auth/login", json={"email": email, "password": OLD_PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert new_login.status_code == 200

    user = db_session.query(User).filter(User.email == email).one()
    assert user.email_verified_at is not None


def test_confirm_replay_is_400_and_password_unchanged(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    email = "ac07-confirm-b@example.com"
    _register(client, email)
    token = _issue_reset_token(client, email, caplog)

    r1 = client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "newPassword": NEW_PASSWORD}
    )
    assert r1.status_code == 204

    r2 = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "newPassword": "yetanotherpassword12"},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == "invalid_token"

    still_new = client.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert still_new.status_code == 200


def test_confirm_expired_token_is_410(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    email = "ac07-confirm-c@example.com"
    _register(client, email)
    token = _issue_reset_token(client, email, caplog)

    row = db_session.get(EmailToken, hash_token(token))
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    r = client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "newPassword": NEW_PASSWORD}
    )
    assert r.status_code == 410
    assert r.json()["detail"] == "token_expired"


def test_confirm_clears_must_change_password_set_by_admin_reset(client_factory, db_session, caplog):
    """Audit finding 8: completing a self-service reset is just another way
    of setting a fresh password, same as `/auth/password` -- it must clear
    `must_change_password` the same way, or the user keeps getting 403
    `password_change_required` on their very next write after "resetting"
    their password."""
    caplog.set_level("INFO", logger="fipm.mail")
    admin = client_factory()
    admin.post(
        "/api/auth/register",
        json={
            "email": "ac07-confirm-mcp-admin@example.com",
            "password": OLD_PASSWORD,
            "displayName": "Admin",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    from fipm.models import User

    admin_user = (
        db_session.query(User).filter(User.email == "ac07-confirm-mcp-admin@example.com").one()
    )
    admin_user.role = "admin"
    db_session.commit()
    admin.post(
        "/api/auth/login",
        json={"email": "ac07-confirm-mcp-admin@example.com", "password": OLD_PASSWORD},
    )

    email = "ac07-confirm-mcp-target@example.com"
    _register(client_factory(), email)
    target_user = db_session.query(User).filter(User.email == email).one()
    reset_r = admin.post(f"/api/admin/users/{target_user.id}/reset-password")
    assert reset_r.status_code == 200, reset_r.text

    db_session.refresh(target_user)
    assert target_user.must_change_password is True

    token = _issue_reset_token(client_factory(), email, caplog)
    confirm = client_factory().post(
        "/api/auth/password-reset/confirm", json={"token": token, "newPassword": NEW_PASSWORD}
    )
    assert confirm.status_code == 204

    db_session.refresh(target_user)
    assert target_user.must_change_password is False

    fresh = client_factory()
    login = fresh.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert login.status_code == 200
    assert login.json()["mustChangePassword"] is False
    me = fresh.get("/api/auth/me")
    assert me.status_code == 200


def test_confirm_invalidates_other_outstanding_reset_tokens(client, db_session, caplog):
    """Audit finding 7: a `password_reset` token consumed by confirm must
    take every other outstanding `password_reset` token for that user with
    it -- otherwise a second, still-unused reset link (e.g. requested
    again before the first was used) keeps working after a reset already
    happened."""
    caplog.set_level("INFO", logger="fipm.mail")
    email = "ac07-confirm-e@example.com"
    _register(client, email)

    token_a = _issue_reset_token(client, email, caplog)
    # `issue_email_token` already deletes the earlier *unused* row when a
    # new one of the same purpose is issued, so insert a second row by hand
    # to model two concurrently outstanding tokens (e.g. issued from two
    # different requests that both landed before either was consumed).
    from datetime import UTC, datetime, timedelta

    from fipm.ids import hash_token, new_token
    from fipm.models import EmailToken, User

    user = db_session.query(User).filter(User.email == email).one()
    token_b = new_token()
    db_session.add(
        EmailToken(
            id=hash_token(token_b),
            user_id=user.id,
            purpose="password_reset",
            email=user.email,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            used_at=None,
        )
    )
    db_session.commit()

    confirm = client.post(
        "/api/auth/password-reset/confirm", json={"token": token_a, "newPassword": NEW_PASSWORD}
    )
    assert confirm.status_code == 204

    replay_b = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token_b, "newPassword": "yetanotherpassword12"},
    )
    assert replay_b.status_code == 400
    assert replay_b.json()["detail"] == "invalid_token"


def test_second_reset_token_deletes_first_unused_one(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    email = "ac07-confirm-d@example.com"
    _register(client, email)
    _issue_reset_token(client, email, caplog)
    _issue_reset_token(client, email, caplog)

    user = db_session.query(User).filter(User.email == email).one()
    rows = (
        db_session.query(EmailToken)
        .filter(EmailToken.user_id == user.id, EmailToken.purpose == "password_reset")
        .all()
    )
    assert len(rows) == 1

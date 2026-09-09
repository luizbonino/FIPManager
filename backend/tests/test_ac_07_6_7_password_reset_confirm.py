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

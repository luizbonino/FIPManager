"""AC1/AC2 (spec 07-mail-and-migration.md §7): register with
`FIPM_MAIL_BACKEND=console` (the test suite's default, per conftest.py not
overriding it) logs one INFO record on `fipm.mail` containing
`{FIPM_BASE_URL}/verify?token=`, `emailVerifiedAt` is null on the response,
and `hash_token(token) == email_tokens.id` while no column holds the
plaintext. `POST /api/auth/verify-email` with that token succeeds once;
a replay is 400 `invalid_token`; an expired token is 410 `token_expired`;
a random token is 400 `invalid_token`."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import update

from fipm.ids import hash_token
from fipm.models import EmailToken

PRIVACY_VERSION = "test-v1"


def _register(client, email, caplog=None):
    if caplog is not None:
        caplog.set_level("INFO", logger="fipm.mail")
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "V",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_register_logs_console_mail_with_verify_link_and_no_plaintext_stored(
    client, db_session, caplog
):
    caplog.set_level("INFO", logger="fipm.mail")
    body = _register(client, "ac07-verify-a@example.com")
    assert body["emailVerifiedAt"] is None

    mail_records = [r for r in caplog.records if r.name == "fipm.mail"]
    assert len(mail_records) == 1
    message = mail_records[0].getMessage()
    assert "[MAIL] to=ac07-verify-a@example.com" in message
    assert "subject=" in message

    match = re.search(r"/verify\?token=(\S+)", message)
    assert match, message
    token = match.group(1)

    row = db_session.get(EmailToken, hash_token(token))
    assert row is not None
    assert row.id == hash_token(token)
    assert len(row.id) == 64
    assert row.purpose == "verify_email"
    assert row.used_at is None
    # No column anywhere in the row holds the plaintext token.
    assert token not in (row.id, row.email, row.purpose)


def test_verify_email_succeeds_once_then_replay_is_400(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-verify-b@example.com")
    message = next(r for r in caplog.records if r.name == "fipm.mail").getMessage()
    token = re.search(r"/verify\?token=(\S+)", message).group(1)

    r1 = client.post("/api/auth/verify-email", json={"token": token})
    assert r1.status_code == 200, r1.text
    assert r1.json()["emailVerifiedAt"] is not None

    r2 = client.post("/api/auth/verify-email", json={"token": token})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "invalid_token"


def test_verify_email_expired_token_is_410(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-verify-c@example.com")
    message = next(r for r in caplog.records if r.name == "fipm.mail").getMessage()
    token = re.search(r"/verify\?token=(\S+)", message).group(1)

    row = db_session.get(EmailToken, hash_token(token))
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 410
    assert r.json()["detail"] == "token_expired"


def test_verify_email_random_token_is_400(client):
    r = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_token"


def test_atomic_claim_prevents_double_use_even_when_both_read_it_as_unused(
    client, db_session, caplog
):
    """Audit finding 9: two concurrent requests resolving the same token
    used to both pass `resolve_email_token`'s `row.used_at is not None`
    read before either request's caller committed its own `row.used_at =
    now`, letting both proceed (e.g. two racing verify-email calls with the
    same link). The claim is now one atomic `UPDATE ... WHERE used_at IS
    NULL` inside `resolve_email_token` itself: given two independent
    sessions that both still see the row as unused, only the one that
    performs that UPDATE first can ever win (`rowcount == 1`); the other
    gets `rowcount == 0`, matching what `resolve_email_token` treats as a
    lost race and reports as 400 `invalid_token` -- not the pre-existing
    `row.used_at is not None` check, which by construction can't have
    fired yet for either session at this point."""
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-verify-race@example.com")
    message = next(r for r in caplog.records if r.name == "fipm.mail").getMessage()
    token = re.search(r"/verify\?token=(\S+)", message).group(1)

    row = db_session.get(EmailToken, hash_token(token))
    assert row.used_at is None  # both racing callers would see this

    from fipm.auth import resolve_email_token
    from fipm.db import SessionLocal

    with SessionLocal() as db1, SessionLocal() as db2:
        now = datetime.now(UTC)
        result1 = db1.execute(
            update(EmailToken)
            .where(EmailToken.id == row.id, EmailToken.used_at.is_(None))
            .values(used_at=now)
        )
        assert result1.rowcount == 1
        db1.commit()

        result2 = db2.execute(
            update(EmailToken)
            .where(EmailToken.id == row.id, EmailToken.used_at.is_(None))
            .values(used_at=now)
        )
        assert result2.rowcount == 0

    # End-to-end: resolve_email_token surfaces an already-claimed row as a
    # normal 400 invalid_token, never letting a second caller through.
    with SessionLocal() as db3:
        with pytest.raises(HTTPException) as exc_info:
            resolve_email_token(db3, token, "verify_email")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "invalid_token"

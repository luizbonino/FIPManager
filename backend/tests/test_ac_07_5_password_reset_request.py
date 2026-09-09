"""AC5 (spec 07-mail-and-migration.md §7): `POST /api/auth/password-reset/
request` -> 202 for a known address (one mail logged, link contains
`/reset-password?token=`) and 202 with no mail and no `email_tokens` row for
an unknown or malformed one -- bodies and codes byte-identical; the 4th call
for one address is still 202 with no mail."""

from __future__ import annotations

from sqlalchemy import select

from fipm.models import EmailToken

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "P",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text


def test_known_address_202_with_one_mail(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-reset-known@example.com")
    caplog.clear()

    r = client.post(
        "/api/auth/password-reset/request", json={"email": "ac07-reset-known@example.com"}
    )
    assert r.status_code == 202
    assert r.text in ("", "null")

    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert len(mail_records) == 1
    message = mail_records[0].getMessage()
    assert "/reset-password?token=" in message


def test_unknown_address_202_no_mail_no_row(client, db_session, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    r = client.post("/api/auth/password-reset/request", json={"email": "nobody-at-all@example.com"})
    assert r.status_code == 202
    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert mail_records == []
    rows = db_session.execute(
        select(EmailToken).where(EmailToken.email == "nobody-at-all@example.com")
    ).all()
    assert rows == []


def test_malformed_address_same_code_and_body_as_unknown(client):
    known = client.post(
        "/api/auth/password-reset/request", json={"email": "still-nobody@example.com"}
    )
    malformed = client.post("/api/auth/password-reset/request", json={"email": "not-an-email"})
    assert known.status_code == malformed.status_code == 202
    assert known.text == malformed.text


def test_fourth_request_for_one_address_still_202_no_mail(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-reset-rate@example.com")

    for _ in range(3):
        r = client.post(
            "/api/auth/password-reset/request", json={"email": "ac07-reset-rate@example.com"}
        )
        assert r.status_code == 202
    caplog.clear()

    r4 = client.post(
        "/api/auth/password-reset/request", json={"email": "ac07-reset-rate@example.com"}
    )
    assert r4.status_code == 202
    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert mail_records == []

"""AC4 (spec 07-mail-and-migration.md §7): `POST /api/auth/verify-email/resend`
-> 202 for an unverified user, 202 with no mail for a verified one, 429 with
`Retry-After` on the 4th call within an hour."""

from __future__ import annotations

import re

PRIVACY_VERSION = "test-v1"


def _register(client, email):
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "R",
            "privacyAcceptedVersion": PRIVACY_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_resend_202_for_unverified_user(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-resend-a@example.com")
    caplog.clear()

    r = client.post("/api/auth/verify-email/resend")
    assert r.status_code == 202

    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert len(mail_records) == 1
    assert "/verify?token=" in mail_records[0].getMessage()


def test_resend_202_no_mail_when_already_verified(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-resend-b@example.com")
    message = next(rec for rec in caplog.records if rec.name == "fipm.mail").getMessage()
    token = re.search(r"/verify\?token=(\S+)", message).group(1)
    verify = client.post("/api/auth/verify-email", json={"token": token})
    assert verify.status_code == 200
    caplog.clear()

    r = client.post("/api/auth/verify-email/resend")
    assert r.status_code == 202
    mail_records = [rec for rec in caplog.records if rec.name == "fipm.mail"]
    assert mail_records == []


def test_resend_429_on_fourth_call_within_an_hour(client, caplog):
    caplog.set_level("INFO", logger="fipm.mail")
    _register(client, "ac07-resend-c@example.com")

    for _ in range(3):
        r = client.post("/api/auth/verify-email/resend")
        assert r.status_code == 202

    r4 = client.post("/api/auth/verify-email/resend")
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers


def test_resend_requires_auth(client):
    r = client.post("/api/auth/verify-email/resend")
    assert r.status_code == 401

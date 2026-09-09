"""AC1: POST /api/auth/register — cookie, argon2id hash, no plaintext, dup email 409."""

from __future__ import annotations

from fipm.db import SessionLocal
from fipm.models import User


def test_register_sets_cookie_and_hashes_password(client):
    email = "ac1-user@example.com"
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "AC1 User",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r.status_code == 201
    assert "fipm_session" in r.cookies

    set_cookie_header = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        assert user.password_hash.startswith("$argon2id$")
        assert "correcthorsebattery" not in user.password_hash


def test_register_duplicate_email_any_case_returns_409(client):
    email = "ac1-dup@example.com"
    r1 = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correcthorsebattery",
            "displayName": "First",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/auth/register",
        json={
            "email": email.upper(),
            "password": "correcthorsebattery",
            "displayName": "Second",
            "privacyAcceptedVersion": "test-v1",
        },
    )
    assert r2.status_code == 409

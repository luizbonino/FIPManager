"""AC2: login success/failure, GET /auth/me, logout, and the 11-failures rate limit."""

from __future__ import annotations


def _register(client, email, password):
    r = client.post(
        "/api/auth/register", json={"email": email, "password": password, "displayName": "AC2"}
    )
    assert r.status_code == 201
    client.post("/api/auth/logout")


def test_login_success_and_wrong_password_and_me_and_logout(client):
    email = "ac2-user@example.com"
    password = "correcthorsebattery"
    _register(client, email, password)

    bad = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid_credentials"

    good = client.post("/api/auth/login", json={"email": email, "password": password})
    assert good.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == email

    client.cookies.clear()
    me_no_cookie = client.get("/api/auth/me")
    assert me_no_cookie.status_code == 401

    client.post("/api/auth/login", json={"email": email, "password": password})
    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 204

    me_after_logout = client.get("/api/auth/me")
    assert me_after_logout.status_code == 401


def test_11_failed_logins_returns_429(client):
    email = "ac2-ratelimit@example.com"
    password = "correcthorsebattery"
    _register(client, email, password)

    last = None
    for _ in range(11):
        last = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert last.status_code == 429
    assert "Retry-After" in last.headers
